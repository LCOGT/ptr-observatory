

# -*- coding: utf-8 -*-
"""
Created on Sun Dec 11 23:27:31 2016

@author: obs
"""

'''

Note this is very old code from first TCS going back to 2015
This code is confusing because it is mixing degree, hour and radian measure in
a way that is not obvious.  Hungarian might help here.

'''

import math
#import threading
import time
from numpy import arange

#import ccd

import datetime as datetime
from datetime import timedelta
import socket
#import struct
import os
import shelve
from collections import namedtuple
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, FK5, ICRS, FK4, Distance, \
                         EarthLocation, AltAz
from astroquery.vizier import Vizier
from astroquery.simbad import Simbad
#from mpl_toolkits.basemap import Basemap



import ephem
#from ptr_astrometrics import *

'''
Obs List
[M48, M67, C25, N2619, M81, M82, N2683, M44, M42, M45, M1, C60, C61]
'''

Target = namedtuple('Target',['ra', 'dec', 'name', 'simbad', 'obj', 'mag', \
                               'size', 'pa', 'ly', 'cdist']) \
#                              #last a string with unit

DEG_SYM = '°'
PI = math.pi
TWOPI = math.pi*2
PIOVER2 = math.pi/2.
DTOR = math.pi/180.
RTOD = 180/math.pi
STOR = math.pi/180./3600.
RTOS = 3600.*180./math.pi
RTOH = 12./math.pi
HTOR = math.pi/12.
HTOS = 15*3600.
DTOS = 3600.
STOD = 1/3600.
STOH = 1/3600/15.
SecTOH = 1/3600.
APPTOSID = 1.00273811906 #USNO Supplement
MOUNTRATE = 15*APPTOSID  #15.0410717859
KINGRATE = 15.029
RefrOn = True

ModelOn = True
RatesOn = True

HORIZON = 9.999   #Lower than actual PTR values.

WESTWESTLIMIT = 5.05
WESTEASTLIMIT = -3.25
EASTWESTLIMIT = 3.25
EASTEASTLIMIT = -5.05

ALTAZ = False

if ALTAZ:
    MOUNT = 'PW L500'
    INTEGRATOR_SIZE = 3
else:
    MOUNT = 'ASA DM-160'
    INTEGRATOR_SIZE = 3

model = {}    #Note model starts out zero
model['IH'] = 0
model['ID'] = 0
model['WH'] = 0
model['WD'] = 0
model['MA'] = 0
model['ME'] = 0
model['CH'] = 0
model['NP'] = 0
model['TF'] = 0
model['TX'] = 0
model['HCES'] = 0
model['HCEC'] = 0
model['DCES'] = 0
model['DCEC'] = 0
model['IA'] = 0
model['IE'] = 0
model['AN'] = 0
model['AW'] = 0
model['CA'] = 0
model['NPAE'] = 0
model['ACES'] = 0
model['ACEC'] = 0
model['ECES'] = 0
model['ECEC'] = 0

modelChanged = False

#Trensfer globals for G_ptr_utility.  This is terrible form!
raCorr = 0.0
decCorr = 0.0
raRefr = 0.0
decRefr = 0.0
refAsec = 0.0
raVel = 0.0
decVel = 0.0

#A series of useful module globals:

jYear = None
JD = None
MJD = None
unixEpochOf = None
jEpoch = 2018.3
gSimulationOffset = 0
gSimulationFlag = False
gSimulationStep = 120           #seconds.

intDay = int(ephem.now())
dayFrac = ephem.now() - intDay
if dayFrac < 0.20833:
    dayNow = intDay - 0.55
else:
    dayNow = intDay + 0.45
ephem.date = ephem.Date(dayNow)
dayStr = str(ephem.date).split()[0]
dayStr = dayStr.split('/')
print('Day String', dayStr)
if len(dayStr[1]) == 1:
    dayStr[1] = '0' + dayStr[1]
if len(dayStr[2]) == 1:
    dayStr[2] = '0' + dayStr[2]
print('Day String', dayStr)
DAY_Directory = dayStr[0] + dayStr[1] + dayStr[2]

#Here is the key code to update a parallel GUI module. These are
#referenced via GUI module via a dedicated import of utility as _ptr_utility.
#NOTE these must be set up by the Gui

ui = None             #for reference to GUI elements
doEvents = None       #path to QApplication.updateEvent function.
modelChanged = False

def zeroModel():
    global modelChanged
    model = {}    #Note model starts out zero
    model['IH'] = 0
    model['ID'] = 0
    model['WH'] = 0
    model['WD'] = 0
    model['MA'] = 0
    model['ME'] = 0
    model['CH'] = 0
    model['NP'] = 0
    model['TF'] = 0
    model['TX'] = 0
    model['HCES'] = 0
    model['HCEC'] = 0
    model['DCES'] = 0
    model['DCEC'] = 0
    model['IA'] = 0
    model['IE'] = 0
    model['AN'] = 0
    model['AW'] = 0
    model['CA'] = 0
    model['NPAE'] = 0
    model['ACES'] = 0
    model['ACEC'] = 0
    model['ECES'] = 0
    model['ECEC'] = 0
    modelChanged = False
    return model

modelChanged = False

def ephemSimNow(offset=None):
    local = ephem.now()
    if gSimulationFlag:
        local += gSimulationOffset/86400.
    if offset is not None:
        local += float(offset)/86400.
    return round(local, 5)

def updateGui():      #What to call from non-GUI modules.
    if doEvents is not None:
        #print('doEvents called in ptr_utility')
        doEvents()

def sleepEvents(pTime):     #Updates GUI often but still returns the required
    st = time.time()        #delay to caller.  Essentially a non-blocking sleep.
    try:
        updateGui()
    except:
        pass
    #pTime = round(pTime, 2)
    while time.time() < st + pTime:
        time.sleep(0.05)
        try:
            updateGui()
        except:
            pass
        continue
    try:
        updateGui()
    except:
        pass



#the init>>> below take a list, query Simbad and assemble currently accurate
#are discarded becuase they are never visible.  The point of these lists
#to to chache the Simbad lookup for speed.


targetList = []
typeList= []
sky2000_list= []
def initNavStars():
    '''
    Get a list of very bright stars, plus a few others, and cull any too
    low to be visible.

    Also obtain official Simbad star name



    '''
    global targetList
    targetList = []
    nav = open ('navigation.txt', 'r')
    j = Simbad()
    j.add_votable_fields('pmra','pmdec')
    for line in nav:
        entry = line.split(',')
        sub = None
        #The following names are not regognized by Simbad. So we fake them.
        if entry[0] == 'Eltanin':
            sub = 'Eltanin'
            entry[0] = 'gam Dra'
        if entry[0] == 'Rigil Kentaurus':
            sub = 'Rigil Kentaurus'
            entry[0] = 'alpha Cen'
        if entry[0] == 'Hadar':
            sub = 'Hadar'
            entry[0] = 'bet Cen'
        if entry[0] == 'Gienah':
            sub = 'Geinah'
            entry[0] = 'gam Crv'

        h = j.query_object(entry[0])
        time.sleep(0.250)
        if sub is not None:
            entry[0] = sub
        #print(entry[0], fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), h['MAIN_ID'].data[0].decode())

        cullDec = -(90 - siteLatitude - HORIZON/2.)
        if float(fromTableDMS(h['DEC'].data[0])) <= cullDec:
            continue
        targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]),  '*' + entry[0],  h['MAIN_ID'].data[0].decode()))
    #print(targetList)
    make_target_list("Navigation Stars")
    return targetList

def initSky2000():
    global target_list
    target_list = []
    sky2000_handle = open('Q:\\astrocatalogs\\skycat\\SKYCAT.DAT', 'rb')
    sky_names_handle = open('Q:\\astrocatalogs\\skycat\\NAMES.DAT', 'rb')
    line_count = 1
    equator_count = 0
    named = 0
    eq = float(equinox_now[3:])
    for line in range(45269):   #45269
        SAO = sky2000_handle.read(6).decode()
        ra = sky2000_handle.read(7).decode()
        ras = float(ra[-3:])/36000.     #36000 is correct.
        ram = float(ra[2:4])/60.
        ra = float(ra[0:2]) + ram + ras

        dec = sky2000_handle.read(7).decode().strip()
       #print(dec)
        decsgn = dec.split('-')
        #print(decsgn)
        if len(decsgn) == 2:
            ds = -1
            decmag = int(decsgn[1])
        else:
           ds = 1
           decmag = int(decsgn[0])
        #print(decmag)
        des = decmag % 100.
        #print(des)
        decmag = (decmag - des)//100
        #print(decmag)
        dem = decmag % 100
        #print (dem)
        decmag = (decmag - dem)//100
        #print(decmag)
        dec = ds*(decmag + dem/60 + des/3600)
        #print(dec)
#


        radot = sky2000_handle.read(5).decode()#()*eq/1000
        decdot = sky2000_handle.read(4).decode()#)*eq/1000

        #print (radot*float(equinox_now[2:]), decdot*float(equinox_now[2:]))
        vmag = sky2000_handle.read(4).decode()
        vmag = vmag[0:2] + '.' + vmag[3:]
        try:
            fvmag = float(vmag)
        except:
            print('Err:  ', line)
        if vmag[0] == '-':
            pass
#        if -15000 <= int(dec) <= 15000:
#            print(line)#+1)
        inList = False
        if -.2 <= int(dec) <= .2 and fvmag <= 6:
            #print(equator_count, ra, len(radot), "'"+radot+"'", dec, len(decdot), "'"+decdot+"'", vmag)

            if radot == '     ': radot = 0.0
            if decdot == '    ': decdot = 0.0
            radot = float(radot)*jNow/1000/3600
            decdot = float(decdot)*jNow/100/3600
            ra = reduceRa(ra + radot)
            dec = reduceDec(dec + decdot)
            print(equator_count, ra, ra + radot, dec, dec + decdot, vmag)
            target_list.append((ra, dec, str(equator_count), str(vmag).strip()))
            equator_count += 1

            inList = True
        b_v = sky2000_handle.read(4).decode()
        spec =  sky2000_handle.read(2).decode()
        rv =  sky2000_handle.read(4).decode()
        dist =  sky2000_handle.read(4).decode()
        dist_flag =  sky2000_handle.read(1).decode()
        index =  sky2000_handle.read(4).decode()
        entry = ''
        if index != '    ':
            int_index = int(index)
            rec_size = 33
            vector = (int_index - 1)*rec_size
            sky_names_handle.seek(vector, 0)
            entry = sky_names_handle.read(rec_size).decode()
            #print(line_count, index, entry)
            if entry[0] != 'A' and inList:
                named += 1

                print('         ',  entry, named)#, vmag, ra,  radot, dec, decdot)
                inList = False
        line_count +=1
        if line >= 45269:
            break
    sky2000_handle.close()
    sky_names_handle.close()
    #print(SAO, b_v, ra)
    return target_list


def init200stars():
    global targetList
    targetList = []
    big = open('TwoHundredStars.txt', 'r+b')
    for line in big:
        entry = line.decode().strip().split()
        print(entry)
        h = Simbad.query_object(entry[0])
        cullDec = -(90 - siteLatitude - HORIZON/2.)
        print(h, '\n', cullDec, fromTableDMS(h['DEC'].data[0]))
        if float(fromTableDMS(h['DEC'].data[0])) <= cullDec:
            continue
        if '*' + entry[1] == '* ':
            targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), h['MAIN_ID'].data[0].decode(),  h['MAIN_ID'].data[0].decode(), entry[-3], entry[-2], entry[-1]))
        else:
            targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]),  '*' + entry[1],  h['MAIN_ID'].data[0].decode(), entry[-3], entry[-2], entry[-1]))
    make_target_list("200 Stars")
    return targetList

def init300stars():
    global targetList
    targetList = []
    big = open('ThreeHundredStars.txt', 'r+b')
    triples = ('Majoris', 'Minoris', 'Borealis', 'Australis', 'Austrini', 'Venaticorum')
    for line in big:
        entry = line.decode().strip().split()
        #print(entry)
        if len(entry) == 18:
            bayer = entry[1] + ' ' + entry[2]
            name = entry[3] + ' ' + entry[4] + ' ' + entry[5] + ' ' + entry[6]
            #print(len(entry), bayer, '|', name)
            entry = entry[-11:]
        if len(entry) == 17:
            if entry[3] in triples:
                bayer = entry[1] + ' ' + entry[2] + ' ' + entry[3]
                name = entry[4] + ' ' + entry[5]
            else:
                bayer = entry[1] + ' ' + entry[2]
                name = entry[3] + ' ' +entry[4] + ' ' + entry[5]
            #print(len(entry), bayer, '|', name)
            entry = entry[-11:]
        if len(entry) == 16:
            if entry[3] in triples:
                bayer = entry[1] + ' ' + entry[2] + ' ' + entry[3]
                name = entry[4]
            else:
                bayer = entry[1] + ' ' + entry[2]
                name = entry[3] + ' ' +entry[4]
            #print(len(entry), bayer, '|', name)
            entry = entry[-11:]
        if len(entry) == 15:
            if entry[3] in triples:
                bayer = entry[1] + ' ' + entry[2] + ' ' + entry[3]
                name = None
            else:
                bayer = entry[1] + ' ' + entry[2]
                name = entry[3]
            #print(len(entry), bayer, '|', name)
            entry = entry[-11:]
        if len(entry) == 14:
            if entry[3] in triples:
                bayer = entry[1] + ' ' + entry[2]
                name = None
            else:
                bayer = entry[1] + ' ' + entry[2]
                name =None
            #print(len(entry), bayer, '|', name)
            entry = entry[-11:]
        if len(entry) == 13:
            if entry[3] in triples:
                bayer = entry[1] + ' ' + entry[2]
                name = "None"
            else:
                bayer = entry[1] + ' ' + entry[2]
                name = None
            #print(len(entry), bayer, '|', name)
            entry = entry[-11:]
        h = Simbad.query_object(bayer)
#        print(h)
        cullDec = -(90 - siteLatitude - HORIZON/2.)
#        print(h, '\n', cullDec, fromTableDMS(h['DEC'].data[0]))
        if float(fromTableDMS(h['DEC'].data[0])) <= cullDec:
            continue
        #print(entry[1])
        simName = h['MAIN_ID'].data[0].decode()
        if simName[0:4] == 'NAME':
            simName = simName[4:]
        if simName[0] == 'V':
            simName = simName[1:]
            if entry[5][-1] != 'v':
                entry[-5] = entry[-5] + 'v'
        if name is None:
            targetList.append((fromTableHMS(h['RA'].data[0]), \
                            fromTableDMS(h['DEC'].data[0]), \
                            simName,  \
                            simName, ' *', \
                            entry[-6], entry[-5]))#, entry[-2], entry[-1]))
        else:
            targetList.append((fromTableHMS(h['RA'].data[0]), \
                            fromTableDMS(h['DEC'].data[0]), \
                            name,  \
                            simName, ' *', \
                            entry[-6], entry[-5]))#, entry[-2], entry[-1]))
    big.close()
    make_target_list("300 Stars")
    return targetList

def initMessier():
    global targetList, typeList
    targetList = []
    mess = open('Messier.txt', 'r')
    count = 0
    for obj in mess:
        entry = obj.split()
        if count < 19:
            ab = entry[0][:2]
            out =''
            for word in range(len(entry[1:])):
                out += entry[1 + word] + ' '
            out = out.strip()
            typeList.append((ab,out))
        if 19 <= count <= 128:
             h = Simbad.query_object(entry[0])
             #print(entry[0], fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), entry[1:6], len(entry[12:]))
             cullDec = -(90 - siteLatitude - HORIZON/2.)
             if float(fromTableDMS(h['DEC'].data[0])) <= cullDec:
                 continue
             if len(entry[12:]) > 0:
                 out = ''
                 for word in range(len(entry[12:])):
                     #print(entry[12 + word])
                     out += entry[12 + word] + ' '
                 targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), out.strip(), entry[0], entry[2], entry[3], entry[4]))
             else:
                 out = ''
                 targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), entry[0], entry[0], entry[2], entry[3], entry[4]))#, entry[4], entry[5], entry[8],   out.strip() ))
        if 129 <= count:
            skip = False
            s = entry[1][0]
            if s == '*' or s == '-':
                skip = True
            elif s == 'I':
                query = 'IC ' + entry[1][1:]
            elif s == 'S':
                query = entry[1]
            else:
                query = 'NGC ' + entry[1]
            #print(query)
            if not skip:
                h = Simbad.query_object(query)
                #print(entry[0], fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), entry[1:6], len(entry[12:]))
                dec = float(fromTableDMS(h['DEC'].data[0]))
                ha = fromTableHMS(h['RA'].data[0])
            else:
                sgn = 1
                if entry[8][0] =='-':
                    sgn = -1
                dec = round(sgn*(float(entry[8][1:]) + float(entry[9])/60.), 4)
                ha = round(float(entry[6]) + float(entry[7])/60., 5)
            cullDec = -(90 - siteLatitude - HORIZON/2)
            if dec <= cullDec:
                continue
            if len(entry[12:]) > 0:
                out = ''
                for word in range(len(entry[12:])):
                    #print(entry[12 + word])
                    out += entry[12 + word] + ' '
                if out.strip()[0:7] =='winter ':
                    out = out.strip()[7:]
                if not skip:
                    targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), out.strip(), query, entry[2], entry[3], entry[4]))# entry[6], entry[10],   out.strip() ))
                else:
                    targetList.append((ha, dec,   out.strip(), query, entry[2], entry[3], entry[4]))
            else:
                out = ''
                if not skip:
                    targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), entry[0], query, entry[2], entry[3], entry[4]))# entry[6], entry[10],   out.strip() ))
                else:
                    print(count, entry)
                    targetList.append((ha, dec,  query, entry[2], entry[3], entry[4]))#, entry[6], entry[10],   out.strip() ))
        count += 1
    make_target_list("Messier-Caldwell")
    return targetList

def initParty():
    global targetList, typeList
    targetList = []
    mess = open('HRW20180408.txt', 'r')
    count = 0
    for obj in mess:
        entry = obj.split()
        if count < 19:
            ab = entry[0][:2]
            out =''
            for word in range(len(entry[1:])):
                out += entry[1 + word] + ' '
            out = out.strip()
            typeList.append((ab,out))
        if 19 <= count <= 36:
             #print(count, entry[0])
             h = Simbad.query_object(entry[0])
             #print(entry[0], fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), entry[1:6], len(entry[12:]))
             cullDec = -(90 - siteLatitude - HORIZON/2.)
             #print(count, entry, h)
             if float(fromTableDMS(h['DEC'].data[0])) <= cullDec:
                 continue
             if len(entry[12:]) > 0:
                 out = ''
                 for word in range(len(entry[12:])):
                     #print(entry[12 + word])
                     out += entry[12 + word] + ' '
                 targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), out.strip(), entry[0], entry[2], entry[3], entry[4]))
             else:
                 out = ''
                 targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), entry[0], entry[0], entry[2], entry[3], entry[4]))#, entry[4], entry[5], entry[8],   out.strip() ))
        if 37 <= count:
            #print(count, entry)
            skip = False
            s = entry[1][0]
            if s == '*' or s == '-':
                skip = True
            elif s == 'I':
                query = 'IC ' + entry[1][1:]
            elif s == 'S':
                query = entry[1]
            else:
                query = 'NGC ' + entry[1]
            #print(query)
            #print(count, entry, query)
            if not skip:
                #print(count, entry)
                h = Simbad.query_object(query)
                #print(entry[0], fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), entry[1:6], len(entry[12:]))
                dec = float(fromTableDMS(h['DEC'].data[0]))
                ha = fromTableHMS(h['RA'].data[0])
            else:
                sgn = 1
                if entry[8][0] =='-':
                    sgn = -1
                dec = round(sgn*(float(entry[8][1:]) + float(entry[9])/60.), 4)
                ha = round(float(entry[6]) + float(entry[7])/60., 5)
            cullDec = -(90 - siteLatitude - HORIZON/2)
            if dec <= cullDec:
                continue
            if len(entry[8:]) > 0:
                out = ''
                for word in range(len(entry[12:])):
                    #print(entry[12 + word])
                    out += entry[12 + word] + ' '
                if out.strip()[0:7] =='winter ':
                    out = out.strip()[7:]
                #print('1: ', count, entry, query, out.strip(), skip)
                if not skip:
                    targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), out.strip(), query, entry[2], entry[3], entry[4]))# entry[6], entry[10],   out.strip() ))
                else:
                    targetList.append((ha, dec, entry[0],  out.strip(), entry[2], entry[3], entry[4]))
            else:
                out = ''
                #print('2: ', count, entry, query, skip)
                if not skip:
                    targetList.append((fromTableHMS(h['RA'].data[0]), fromTableDMS(h['DEC'].data[0]), entry[0], query, entry[2], entry[3], entry[4]))# entry[6], entry[10],   out.strip() ))
                else:
                    targetList.append((ha, dec, entry[0], query, entry[2],  entry[3], entry[4]))#, entry[6], entry[10],   out.strip() ))
        count += 1
    make_target_list('HRW20180408')
    return targetList

#Creates a shelved preculled target list.
def make_target_list(targetListName):
    global targetList
    targetShelf = shelve.open('Q:\\ptr_night_shelf\\' + str(targetListName))
    targetShelf['Targets'] = targetList
    targetShelf.close()
    return targetList

def get_target_list(targetListName):
    global targetList
    targetShelf = shelve.open('Q:\\ptr_night_shelf\\' + str(targetListName))
    targetList =targetShelf['Targets']
    targetShelf.close()
    return targetList


#def plotMap(objects, lon):
#    #sidTime = Time(localEpoch,  scale='utc', location=(str(siteLongitude), str(siteLatitude))).sidereal_time('apparent').hour
#    #sidTime = sidTime.sidereal_time('apparent')*15
#    map = Basemap(projection='aeqd', lat_0=siteLatitude, lon_0=lon*15)
#    # draw coastlines, country boundaries, fill continents.
#    #map.drawcoastlines(linewidth=0.25)
#    #map.drawcountries(linewidth=0.25)
#    #map.fillcontinents(color='coral',lake_color='aqua')
#    # draw the edge of the map projection region (the projection limb)
#    map.drawmapboundary(fill_color='aqua')
#    # draw lat/lon grid lines every 30 degrees.
#    map.drawmeridians(np.arange(0,360,15))
#    map.drawparallels(np.arange(-90,90,15))
#    # make up some data on a regular lat/lon grid.
##    nlats = 73; nlons = 145; delta = 2.*np.pi/(nlons-1)
##    lats = (0.5*np.pi-delta*np.indices((nlats,nlons))[0,:,:])
##    lons = (delta*np.indices((nlats,nlons))[1,:,:])
##    wave = 0.75*(np.sin(2.*lats)**8*np.cos(4.*lons))
##    mean = 0.5*np.cos(2.*lats)*((np.sin(2.*lats))**2 + 2.)
##    # compute native map projection coordinates of lat/lon grid.
##    x, y = map(lons*180./np.pi, lats*180./np.pi)
##    # contour data over the map.
##    cs = map.contour(x,y,wave+mean,15,linewidths=1.5)
#    lats = []
#    lons = []
#    for item in targetList:
#        lats.append(item[1])
#        lons.append(item[0]*15)
#    x, y = map(lons,lats)
#    map.scatter(x,y, marker='o', color='k')
#    plt.show
#
#    plt.title('contour lines over filled continent background')
#    plt.show()
#
#
#
#    return

def distSortTargets(pRa, pDec, pSidTime):
    '''
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    '''
    #print(pRa, pDec, pSidTime)
    global targetList

    c1 = SkyCoord(ra=pRa*u.hr, dec=pDec*u.deg)
    sortedTargetList = []
    for star in targetList:
        if horizonCheck(star[0], star[1], pSidTime):
            c2 = SkyCoord(ra=star[0]*u.hr, dec=star[1]*u.deg)
            sep = c1.separation(c2)
            sortedTargetList.append((sep.degree, star))
    sortedTargetList. sort()
    #print('distSortTargets', len(targetList), targetList, '\n\n')
    #print('distSortTargets', len(sortedTargetList), SortedTargetList, '\n\n')
    return sortedTargetList

def zSortTargets(pRa, pDec, pSidTime):
    '''
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    '''
    #print(pRa, pDec, pSidTime)
    global targetList
    c1 = SkyCoord(ra=pRa*u.hr, dec=pDec*u.deg)
    sortedNavList = []
    for star in targetList:
        if horizonCheck(star[0], star[1], pSidTime):
            c2 = SkyCoord(ra=star[0]*u.hr, dec=star[1]*u.deg)
            sep = c1.separation(c2)
            sortedNavList.append((sep.degree, star))
    sortedNavList.sort()
    #print(sortedNavList)
    return sortedNavList

def haSortTargets(pSidTime):
    '''
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    '''
    #print(pRa, pDec, pSidTime)
    global targetList
    haSortedTargets = []
    for star in targetList:
        if horizonCheck(star[0], star[1], pSidTime):
            #print(star)
            ha = reduceHa(pSidTime - star[0])
            haSortedTargets.append((ha, star))
    #print(haSortedTargets)
    haSortedTargets.sort()
    haSortedTargets.reverse()
    #print(sortedNavList)
    return haSortedTargets

def riseSortTargets(pRa, pDec, pSidTime):
    '''
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    '''
    #print(pRa, pDec, pSidTime)
    global targetList
    riseSortedTargets= []
    for star in targetList:
        up, rise, set = riseHorizonCheck(star[0], star[1],  pSidTime)
        if up or rise:
            ha = reduceHa(pSidTime - star[0])
            riseSortedTargets.append((ha, rise, set, star))
    riseSortedTargets.sort()
    return riseSortedTargets

def horizonCheck(pRa, pDec, pSidTime):
    '''
    Check if incoming Ra and Dec object is visible applying the site horizon,
    returning True if it is.  Note temporary added restriction on HA.
    '''
    iHa = reduceHa(pSidTime - pRa)
    if abs(iHa) <= 9:
        az, alt = transform_haDec_to_azAlt(iHa, pDec)
        horizon = calculate_ptr_horizon(az,alt)
        if alt >= horizon:
            #print('found one: ', alt, iHa)
            return True
        else:
            return False
    else:
        return False

def riseHorizonCheck(pRa, pDec, pSidTime):
    '''
    Check if incoming Ra and Dec object is visible applying the site horizon,
    returning True if it is.  differnt criteria E vs. W.
    '''
    iHa = reduceHa(pSidTime - pRa)
    #if abs(iHa) <= 5.75:
    az, alt = transform_haDec_to_azAlt(iHa, pDec, siteLatitude)
    horizon = calculate_ptr_horizon(az,alt)
    rise = False
    set = False
    up = False
    if alt >= horizon:
        #print('found one')
        up = True
    if az < 180 and (horizon - 15) <= alt < horizon:
        rise = True
    if az >= 180 and horizon <  alt <= (horizon + 15):
        set = True
    return up, rise, set


lastBright = 0
def getSkyBright():

    '''
    Correcct Unihedron to be linear compared to
    calculated sky, with one breakpoint at about 7150 Unihedron counts.

    Light leakage is a farily complex function of brightness and is
    basically not predicable.
    data taken June 28, 2017
    '''
    global lastBright
#    bright = open('Q:\\unihedron1\\uniBright.txt', 'r')
#    skyBright = bright.read()
#    bright.close()
    skyBright = core1_redis.get('unihedron1').split(',')
    #print('inget, raw: ', skyBright)
 #   skyBright = skyBright.split(',')
    #print("raw Read:  ", skyBright[1][:-1])
    #print('getSkyBright  1 try:  ',skyBright)
    if len(skyBright) == 2:
        lastBright = int(skyBright[0])
#        if lastBright <= 7150:
#            lastBright  = int(1.0E-08*lastBright*lastBright + \
#                          0.0051*lastBright +90.592)
#            #A modest correction.
#        else:
#            lastBright = int( 0.0153*lastBright*lastBright - \
#                         16589*lastBright + 5.0E09)
#            #Very non-linear and insensitive above break.
        return lastBright, float(skyBright[1])
    else:
        print('this code needs fixing!  Returned: ', skyBright)
#        bright = open('Q:\\unihedron1\\uniBright.txt', 'r')
#        skyBright = bright.read().split(',')
#        #print('SKYBRIGHT:  ', skyBright)
#        bright.close()
#        lastBright = int(skyBright[1])
#        print('getSkyBright  second try, using:  ', skyBright)
##        if len(skyBright) == 2:
##            return int(skyBright[1][:-1])
##        else:
        return lastBright, '999999.'


lastBoltReading = ['2016-11-10', '18:19:10.27', 'C','K', '', \
'-99.9', '', '', '33.8', '', '', '48.7', '', '', '', '0.0', \
'', '23', '', '', '', '9.5', '', '', '0', '0', '0', '00002', \
'042684.76331', '1', '1', '1', '3', '1\n']
def getBoltwood():
    global lastBoltReading
    bolt = open('Q:\\boltwood1\\boltwood1.txt', 'r')
    boltSky = bolt.read().split(' ')
    bolt.close()
    if len(boltSky) == 33:
        #print('Boltwood  1 try:  ', boltSky, len(boltSky))
        lastBoltReading = boltSky
        return boltSky
    else:
        bolt = open('Q:\\boltwood1\\boltwood1.txt', 'r')
        boltSky = bolt.read().split(' ')
        bolt.close()
        lastBoltReading = boltSky
        #print('Last Boltwood reading was replaced by this; ', lastBoltReading)
        return lastBoltReading


def getBoltwood2():
    bws = getBoltwood()
    time = bws[1]
    sky = (bws[5])
    temp = (bws[8])
    wind = float(bws[15])
    if wind < 0:
        wind = "0.0"
    else:
        wind = bws[15]
    hum = (bws[17])
    dew = (bws[20])
    cld  = bws[28]
    wc = bws[29]
    rc = bws[30]
    d = bws[31]
    close = bws[32][0]
    if close == '1':
        close= "True"
    else:
        close = "False"
    return time, sky, temp, dew, hum, wind, close


##FOLOWING ARE MOSTLY STRING FORMAT COVERSIONS

DEGSPLIT = ['d', 'D', '*', '°', ':', ';', '   ', '  ', ' ', "'", '"', 'M', 'm', 'S', 's']
HOURSPLIT = ['h', 'H', ':', ';', '   ', '  ', ' ', 'M', 'm', 'S', 's', "'", '"']


def clean(p):
    return p.strip('#')

def multiSplit(pStr, pChrList):
    #This function is intended to return a split list retruning
    #parsed numeric fields with varoius possible seperators.
    for splitChr in pChrList:
        s_str = pStr.split(splitChr)
        if len(s_str) > 1:
            return (s_str, splitChr)
    return [s_str]



def zFill(pNum, sign=False, left=0, mid=0, right=0):
    #Assume an incoming string with truncated leading zero, leading +, or
    #or trailing 0 to fill out a length.
    if right > 1:
        fFactor= right - len(str(pNum))
        return str(pNum) + '0'*fFactor
    elif mid > 1:
        fFactor = mid - len(str(pNum))
        return '0'*fFactor + str(pNum)
    elif left >1:
        fFactor = left - len(str(pNum))
        return '0'*fFactor + str(pNum)

def fromTableDMS(p):
    sgn = 1
    if p[0] == '-':
        sgn = -1
    p = p[1:].split()
    if len(p) == 2:
        p.append('00')
    d = sgn*(abs(float(p[0])) + (float(p[2])/60. + float(p[1]))/60)
    return round(d, 4)

def fromTableHMS(p):
    p = p.split()
    if len(p) == 2:
        p.append('00')
    h = (abs(float(p[0])) + (float(p[2])/60. + float(p[1]))/60)
    if h > 24:
        h -=  24
    if h < 0:
        h += 24
    return round(h,5)

def getBlankZero(p):
    try:
        bz = float(p)
    except:
        bz = 0.0
        print('ptest: ', '|'+p+'|', len(p))
        if len(p) >= 1 and p[0] == '-':
            bz = bz    #This code can be eliminated
    return bz

def fromDMS(p):

#    #NBNBNB THIS CODE NEEDS FIXING AS BELOW WAS repaired.
#
#    d_ms = multiSplit(clean(p), DEGSPLIT)
#    d = d_ms[0][0]
#    ds = d_ms[0][0][0]
#    dr = abs(float(d))
#    #print(d[0]
#    m=0
#    s = 0
#    if len(d_ms[0]) >= 2:
#        m = float(d_ms[0][1])
#    if len(d_ms[0]) == 3:
#        m = float(d_ms[0][2])
#    if ds != '-':
#        deg = float(dr) + float(m)/60. + float(s)/3600.
#    else:
#        deg = -(float(dr) + float(m)/60. + float(s)/3600.)
#    return deg
    #print('p: ', p)
    sign = 1
    d_ms = multiSplit(clean(p.strip()), DEGSPLIT)
    if d_ms[0][0][0] == '-':
        sign = -1
        d_ms[0][0] = d_ms[0][0][1:]
    #print('d_ms: ', d_ms)

    if len(d_ms[0]) == 3:
        #This is an h m s format
        if d_ms[0][0][-1] in DEGSPLIT:
             d_ms[0][0] = d_ms[0][0][:-1]
        if d_ms[0][1][-1] in DEGSPLIT:
             d_ms[0][1] = d_ms[0][1][:-1]
        if d_ms[0][2][-1] in DEGSPLIT:
            d_ms[0][2] = d_ms[0][2][:-1]
        hr = getBlankZero(d_ms[0][0]) + getBlankZero(d_ms[0][1])/60 + getBlankZero(d_ms[0][2])/3600
        #print('1dms.0: ', hr)
    if len(d_ms[0]) == 2:
        #print('d_ms: ', d_ms)
        m_s = multiSplit(clean(d_ms[0][1]), DEGSPLIT)
       # print ('m_s: ', m_s)
        if m_s[0][0] == '':
            m_s = (m_s[0][1:], m_s[1])

        if len(m_s[0]) == 2:
            if m_s[0][0][-1] in DEGSPLIT:
                m_s[0][0] = m_s[0][0][:-1]
            if m_s[0][1][-1] in DEGSPLIT:
                m_s[0][1] = m_s[0][1][:-1]
            hr =  getBlankZero(d_ms[0][0]) + getBlankZero(m_s[0][0])/60 + getBlankZero(m_s[0][1])/3600
           # print('2dms.0: ', hr)
        if len(m_s[0]) == 1:
            if d_ms[0][0][-1] in DEGSPLIT:
                d_ms[0][0] = d_ms[0][0][:-1]
            if m_s[0][0][-1] in DEGSPLIT:
                m_s[0][0] = m_s[0][0][:-1]
            hr =  getBlankZero(d_ms[0][0]) + getBlankZero(m_s[0][0])/60
            #print('3dms.0: ', hr)
        if len(d_ms[0]) == 1:
            if d_ms[0][0][-1] in DEGSPLIT:
                d_ms[0][0] = d_ms[0][0][:-1]
            hr = getBlankZero(d_ms[0][0])
            #print('4dms.0: ', hr)

    return round(sign*hr, 4)

def fromHMS(p):
    #get frome one to three fields.
    #leading with + or - indicates HA  NOT IMPLEMENTED
    #Empty input means -- Enter LST for RA or Ha = 0  NOT IMPLEMENTED

    #print('p: ', p)
    h_ms = multiSplit(clean(p.strip()), HOURSPLIT)
    #print('h_ms: ', h_ms)

    if len(h_ms[0]) == 3:
        #This is an h m s format
        if h_ms[0][0][-1] in HOURSPLIT:
             h_ms[0][0] = h_ms[0][0][:-1]
        if h_ms[0][1][-1] in HOURSPLIT:
             h_ms[0][1] = h_ms[0][1][:-1]
        if h_ms[0][2][-1] in HOURSPLIT:
            h_ms[0][2] = h_ms[0][2][:-1]
        hr = getBlankZero(h_ms[0][0]) + getBlankZero(h_ms[0][1])/60 + getBlankZero(h_ms[0][2])/3600
        #print('1hms.0: ', hr)
    if len(h_ms[0]) == 2:
        #print('h_ms: ', h_ms)
        m_s = multiSplit(clean(h_ms[0][1]), HOURSPLIT)
        #print ('m_s: ', m_s)
        if m_s[0][0] == '':
            m_s = (m_s[0][1:], m_s[1])

        if len(m_s[0]) == 2:
            if m_s[0][0][-1] in HOURSPLIT:
                m_s[0][0] = m_s[0][0][:-1]
            if m_s[0][1][-1] in HOURSPLIT:
                m_s[0][1] = m_s[0][1][:-1]
            hr =  getBlankZero(h_ms[0][0]) + getBlankZero(m_s[0][0])/60 + getBlankZero(m_s[0][1])/3600
            #print('2hms.0: ', hr)
        if len(m_s[0]) == 1:
            if h_ms[0][0][-1] in HOURSPLIT:
                h_ms[0][0] = h_ms[0][0][:-1]
            if m_s[0][0][-1] in HOURSPLIT:
                m_s[0][0] = m_s[0][0][:-1]
            hr =  getBlankZero(h_ms[0][0]) + getBlankZero(m_s[0][0])/60
            #print('3hms.0: ', hr)
        if len(h_ms[0]) == 1:
            if h_ms[0][0][-1] in HOURSPLIT:
                h_ms[0][0] = h_ms[0][0][:-1]
            hr = getBlankZero(h_ms[0][0])
            #print('4hms.0: ', hr)

    return round(hr, 5)

    #round(fromHMS(p), 5)


def fromDate(p):
    m_d_y = clean(p).split('/')
    #print(m_d_y
    y = int(m_d_y[2])
    if y >= 97:
        y +=1900
    else:
        y +=2000
    d = int(m_d_y[1])
    m = int(m_d_y[0])
    return str(y*10000 + m*100 + d)

def dToHMS(p, short=False):
    while p < 0:
       p += 360
    signed = ''
    if p < 0:
        signed = '-'
    h = abs(p)
    h = h/15.
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h*1000)/1000.
    #print(signed, ih, im, s3
    return signed + str(ih) + "h" + str(im) + "m" + zFill(s, left=2) + "s"

def hToHMS(p, short=False):
    while p >=24:
       p -= 24.
    signed = ''
    if p < 0:
        signed = '-'
    h = abs(p)
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h*1000)/1000.
    #print(signed, ih, im, s
    return signed + str(ih) + "h" + str(im) + "m" + zFill(s, left=2) + "s"

def hToH_MS(p, short=False):
    while p >=24:
       p -= 24.
    signed = ''
    if p < 0:
        signed = '-'
    h = abs(p)
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h*1000)/1000.
    #print(signed, ih, im, s
    return signed + str(ih) + " " + str(im) + " " + zFill(s, left=2)

def hToH_MStup(p, short=False):
    while p >=24:
       p -= 24.
    signed = ''
    if p < 0:
        signed = '-'
    h = abs(p)
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h*1000)/1000.
    #print(signed, ih, im, s
    return (signed + str(ih), str(im), str(s))

def hToH_M(p, short=False):
    while p >=24:
       p -= 24.
    signed = ''
    if p < 0:
        signed = '-'
    h = abs(p)
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
#    if short:
#        s = int(h)
#    else:
#        s = int(h*1000)/1000.
    #print(signed, ih, im, s
    return signed + str(ih) + " " + str(im)    # + " " + str(s)

#NBNB Does anyone call this?
def toDMS(p, short=False):
    signed = '+'
    if p < 0:
        signed = '-'
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d*10)/10.
    if short:
        s = int(d)
    else:
        s = int(d*100)/100.
    #print(signed + str(idec)+ " " + str(im)+ " " + str(s)
    return signed + str(ideg) + "*" + str(im) + "m" + zFill(s, left=2) + 's'

def dToDMS(p, short=False):
    signed = '+'
    if p < 0:
        signed = '-'
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d*10)/10.
    if short:
        s = int(d)
    else:
        s = int(d*100)/100.
    #print(signed + str(idec)+ " " + str(im)+ " " + str(s)
    return signed + str(ideg) + DEG_SYM + str(im) + "m" + zFill(s, left=2) + 's'

def dToDMSdsym(p, short=False):
    signed = '+'
    if p < 0:
        signed = '-'
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d*10)/10.
    if short:
        s = int(d)
    else:
        s = int(d*100)/100.
    #print(signed + str(idec)+ " " + str(im)+ " " + str(s)
    return signed + str(ideg) + DEG_SYM + str(im) + "m" + zFill(s, left=2) + 's'


def dToD_MS(p, short=False):
    signed = '+'
    if p < 0:
        signed = '-'
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d*10)/10.
    if short:
        s = int(d)
    else:
        s = int(d*100)/100.
    #print(signed + str(idec)+ " " + str(im)+ " " + str(s)
    return signed + str(ideg) + " " + str(im) + " " + zFill(s, left=2)

def dToD_MStup(p, short=False):
    signed = '+'
    if p < 0:
        signed = '-'
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d*10)/10.
    if short:
        s = int(d)
    else:
        s = int(d*100)/100.
    #print(signed + str(idec)+ " " + str(im)+ " " + str(s)
    return (signed + str(ideg), str(im), str(s))

def toPier(pSideOfPier):
    if pSideOfPier == False:
        return 'WEST'
    else:
        return 'EAST'

#NBNBNB THis should be a configuration
def toTel(pSideOfPier):
    if pSideOfPier == EASTSIDE:
        return EastSideDesc
    else:
        return WestSideDesc

def toMechHMS(p, short=False):
    while p < 0:
       p += 360
    signed = ' '
    if p < 0:
        signed = '-'
    h = abs(p)
    h = h/15.
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -=im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h*1000)/1000.
    #print(signed + str(ih)+ "" + str(im)+ " " + str(s)
    return signed + str(ih) + ":" + str(im) + ":" + str(s)

def toMechDMS(p, short=False):
    signed = '+'
    if p < 0:
        signed = '-'
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d*10)/10.
    if short:
        s = int(d)
    else:
        s = int(d*100)/100.
    #print(signed + str(idec)+ " " + str(im)+ " " + str(s)
    return signed + str(ideg) + ":" + str(im) + ":" + str(s)

def fixTail(p):
    while p[-1] == '#':
         p.pop(-1)
    return(p)

#These function do not work for mechanical coordinates.
def reduceHa(pHa):
    while pHa <= -12:
        pHa += 24.0
    while pHa > 12:
        pHa -= 24.0
    return pHa

def reduceRa(pRa):
    while pRa < 0:
        pRa += 24.0
    while pRa >= 24:
        pRa -= 24.0
    return pRa

def reduceDec( pDec):
    if pDec > 90.0:
        pDec = 90.0
    if pDec < -90.0:
        pDec = -90.0
    return pDec

def reduceAlt(pAlt):
    if pAlt > 90.0:
        pAlt = 90.0
    if pAlt < -90.0:
        pAlt = -90.0
    return pAlt

def reduceAz(pAz):
    while pAz < 0.0:
        pAz += 360
    while pAz >= 360.0:
        pAz -= 360.0
    return pAz



def raAvg(pFirst,pNext):
    '''Creates a correct average over 0 to 23.999 hour transition'''

    #Note to average RAa/Dec pairs requires considering overpole travel.
    #That is best done with direction cosines and report the average vector.

    delta = abs(pFirst - pNext)
    if delta >= 12:
        small = min(pFirst, pNext)
        small += 24
        avg = (small + max(pFirst, pNext))/2.
        while avg >= 24:
            avg -= 24
        return avg
    else:
        return (pFirst + pNext)/2. #Note there are two possible answers in this situation.
    return

def azAvg(pFirst,pNext):
    '''Creates a correct average over 0 to 359.999 hour transition'''
    delta = abs(pFirst - pNext)
    if delta >= 180:
        small = min(pFirst, pNext)
        small += 360
        avg = (small + max(pFirst, pNext))/2.
        while avg >= 360:
            avg -= 360
        return avg
    else:
        return (pFirst + pNext)/2.
    return



#def test_misAlign():
#    stars = open('TPOINT\\perfct34.dat', 'r')
#    out = open('TPOINT\\misalign.dat', 'w')
#    for line in stars:
#        if len(line) < 53:
#            out.write(line)
#            #print(line)
#            continue
#        entry = line[:]
#        entry = entry.split()
#        #print(entry)
#        h = float(entry[0]) + (float(entry[1]) + float(entry[2])/60.)/60.
#        d = float(entry[3][1:]) + (float(entry[4]) + float(entry[5])/60.)/60.
#        sid = float(entry[12]) + float(entry[13])/60.
#        if entry[3][0] == '-':
#            d = -d
#        ha = reduceHa(sid - h)
##        if ha < 0: pFlip = True
#        pFlip = False
#        iroll, npitch = transformObsToMount(ha, d, False)
###       print(h, d, ha, iroll, npitch)
##        #nroll = reduceRa(sid - iroll)
##        if ha < 0:
##            #print(h, d, ha, iroll, 180 - npitch)
##            nroll = 180 - npitch
##        else:
##        if ha >= 0:
#        nroll = reduceRa(sid - iroll)
##        print(h, d, ha, nroll, npitch)
##        nroll = iroll
#        mh, mm, ms = hToH_MStup(nroll)
#        md, dm, ds = dToD_MStup(npitch)
#        entry[6] = mh
#        entry[7] = mm
#        entry[8] = ms
#        entry[9] = md
#        entry[10] = dm
#        entry[11] = ds
#        #print('entry', entry)
#        outStr = ''
#        for field in range(len(entry)):
#            outStr += entry[field] +"  "
#        outStr = outStr[:-2]
#        #NBNBNB Fix to copy over Sidtime and Aux variables.
#        out.write(outStr +'\n' )
#        #print(outStr+ '  00  00 \n')
#    stars.close()
#    out.close()

def nextSeq(pCamera):
    global SEQ_Counter
    camShelf = shelve.open('Q:\\ptr_night_shelf\\' + pCamera)
    #print('Shelf:  ', camShelf)
    sKey = 'Sequence'
    #print(type(sKey), sKey)
    seq = camShelf[sKey]      #get an 8 character string
    seqInt = int(seq)
    seqInt += 1
    seq = ('0000000000'+str(seqInt))[-8:]
    #print(pCamera,seq)
    camShelf['Sequence'] = seq
    camShelf.close()
    SEQ_Counter = seq
    return seq

def next_seq(pCamera):
    global SEQ_Counter
    camShelf = shelve.open('Q:\\ptr_night_shelf\\' + pCamera)
    #print('Shelf:  ', camShelf)
    sKey = 'Sequence'
    #print(type(sKey), sKey)
    seq = camShelf[sKey]      #get an 8 character string
    seqInt = int(seq)
    seqInt += 1
    seq = ('0000000000'+str(seqInt))[-8:]
    #print(pCamera,seq)
    camShelf['Sequence'] = seq
    camShelf.close()
    SEQ_Counter = seq
    return seq

def makeSeq(pCamera):
    camShelf = shelve.open('Q:\\ptr_night_shelf\\' + str(pCamera))
    #seq = camShelf['Sequence']      # a 9 character string
    seqInt = int(-1)
    seqInt  += 1
    seq = ('0000000000'+str(seqInt))[-8:]
    print('Making new seq: ' , pCamera, seq)
    camShelf['Sequence'] = seq
    camShelf.close()
    return seq





#vega = SkyCoord.from_name('Vega')
#vega.transform_to(FK5(equinox=equinox_now))

#vega_altaz=vega.transform_to(AltAz(obstime=ut_now, location=ptr, pressure=press, temperature=temp, relative_humidity = hum))
#print(vega_altaz.alt.deg, vega_altaz.az.deg)

class Pointing(object):

   def __init__(self):
       self.ra = 0.0            #hours
       self.raDot = 0.0         #asec/s
       self.raDotDot = 0.0      #asec/s/s  Dot-Dots computed over end period
       self.dec = 0.0           #degrees
       self.decDot = 0.0        #asec/s
       self.decDotDot = 0.0     #asec/s/s
       self.sys = 'ICRS'        #The coordinate system
       self.epoch = None        # eg ephem.now()  When the pointing was last
                                #                 computed exactly with Dot
       self.end = None          #seconds, eg 3600 implies valid for 1 hour.
       self.name = 'undefined'  #The name of the pointing.
       self.cat = None          #The catalog Name
       self.cat_no = ''         #A string representing catalog entry


   def haAltAz(self):
       pass      #Some calculations here
       return (ha, alt, az)         #hours, degrees, degrees

   def haAltAzDot(self):
       pass      #Some calculations here
       return (haDot, altDot, azDot)         #asec/s, asec/s, asec/ss

def get_current_times():
    ut_now = Time(datetime.datetime.now(), scale='utc', location=siteCoordinates)   #From astropy.time
    sid_now = ut_now.sidereal_time('apparent')
    sidTime = sid_now
# =============================================================================
#     THIS NEEDS FIXING! Sloppy
# =============================================================================
    iso_day = datetime.date.today().isocalendar()
    doy = ((iso_day[1]-1)*7 + (iso_day[2] ))
    equinox_now = 'J' +str(round((iso_day[0] + ((iso_day[1]-1)*7 + (iso_day[2] ))/365), 2))
    return(ut_now, sid_now, equinox_now, doy)

def calculate_ptr_horizon(pAz,pAlt):
    if pAz  <= 30:
        hor = 35.
    elif pAz <= 36.5:
        hor = 39
    elif pAz <= 43:
        hor = 42.7
    elif pAz <= 59:
        hor = 32.7
    elif pAz <= 62:
        hor = 28.6
    elif pAz <= 65:
        hor = 25.2
    elif pAz <= 74:
        hor = 22.6
    elif pAz <= 82:
        hor = 20
    elif pAz <= 95.5:
        hor =17.2
    elif pAz <= 101.5:
        hor = 14
    elif pAz <= 107.5:
        hor = 10
    elif pAz <=130:
        hor = 11
    elif pAz <= 150:
        hor = 20
    elif pAz <= 172:
        hor = 28
    elif pAz <= 191:
        hor = 25
    elif pAz <= 213:
        hor = 20
    elif pAz <= 235:
        hor = 15.3
    elif pAz <= 260:
        hor = 10.5
    elif pAz <= 272:
        hor = 17
    elif pAz <= 294:
        hor = 16.5
    elif pAz <= 298.5:
        hor = 18.6
    elif pAz <= 303:
        hor = 20.6
    elif pAz <= 309:
        hor =27
    elif pAz <= 315:
        hor =32
    elif pAz <= 360.1:
        hor = 32
    else:
        hor = 15
    if hor < 17:
        hor =17  #Temporary fix for L500
    return hor

def convertToMechanical(pRa, pDec, pFlip):
    if pFlip == 'East':
        return (pRa, pDec)
    else:
        fDec = 180. - pDec
        pRa += 12.
        while pRa >= 24:
            pRa -= 24.
        while pRa < 0.:
            pRa += 24.
        return (pRa, fDec)

def rectSph(pX, pY, pZ):
    rSq = pX*pX + pY*pY + pZ*pZ
    return math.degrees(math.atan2(pY, pX)), math.degrees(math.asin(pZ/rSq))

def sphRect(pRoll, pPitch):
    pRoll = math.radians(pRoll)
    pPitch = math.radians(pPitch)
    cPitch = math.cos(pPitch)
    return math.cos(pRoll)*cPitch, math.sin(pRoll)*cPitch, math.sin(pPitch)

def rotate(pX, pY, pTheta):
    cTheta = math.cos(pTheta)
    sTheta = math.sin(pTheta)
    return pX * cTheta - pY * sTheta, pX * sTheta + pY * cTheta

def transform_raDec_to_haDec(pRa, pDec, pSidTime):
    return (reduceHa(pSidTime - pRa), reduceDec(pDec))

def transformHatoRaDec(pHa, pDec, pSidTime):
    return (reduceRa(pSidTime - pHa), reduceDec(pDec))

def transform_haDec_to_azAlt(pLocal_hour_angle, pDec, lat=siteLatitude):
    latr = math.radians(lat)
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    decr = math.radians(pDec)
    sinDec = math.sin(decr)
    cosDec = math.cos(decr)
    mHar = math.radians(15.*pLocal_hour_angle)
    sinHa = math.sin(mHar)
    cosHa = math.cos(mHar)
    altitude = math.degrees(math.asin(sinLat*sinDec + cosLat*cosDec*cosHa))
    y = sinHa
    x = cosHa*sinLat - math.tan(decr)*cosLat
    azimuth = math.degrees(math.atan2(y, x)) + 180
    azimuth = reduceAz(azimuth)
    altitude = reduceAlt(altitude)
    return (azimuth, altitude)#, local_hour_angle)

def transform_azAlt_to_HaDec(pAz, pAlt, lat=siteLatitude):
    latr = math.radians(lat)
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    alt = math.radians(pAlt)
    sinAlt = math.sin(alt)
    cosAlt = math.cos(alt)
    az = math.radians(pAz - 180)
    sinAz = math.sin(az)
    cosAz = math.cos(az)
    if abs(abs(alt) - PIOVER2) < 1.0*STOR:
        return (0.0, reduceDec(lat))     #by convention azimuth points South at local zenith
    else:
        dec = math.asin(sinAlt*sinLat - cosAlt*cosAz*cosLat)
        ha = math.atan2(sinAz, (cosAz*sinLat + math.tan(alt)*cosLat))
        return (reduceHa(ha*RTOH), reduceDec(dec*RTOD))

def transform_azAlt_to_RaDec(pAz, pAlt, pLatitude, pSidTime):
    ha, dec = transform_azAlt_to_HaDec(pAz, pAlt, pLatitude)
    return transformHatoRaDec(ha, dec, pSidTime)

def test_haDec_AltAz_haDec():
    lHa = [-12, -11.99, -6, -5, -4, -3, -2, -1, 0, 1, 3, 5, 7, 9, 11.999, 12]
    lDec = [-50, -40, -30, -10, 0, 30, siteLatitude, 40, 70, 89.99, 90]
    for ha in lHa:
        for dec in lDec:
            print('Starting:  ', ha, dec)
            lAz, lAlt = transform_haDec_to_azAlt(ha, dec, siteLatitude)
            tHa, tDec = transform_azAlt_to_HaDec(lAz, lAlt, siteLatitude)
            print (ha, tHa, dec, tDec)

def apply_refraction_inEl(pAppEl, pSiteRefTemp, pSiteRefPress): #Deg, C. , mmHg
    #From Astronomical Algorithms.  Max error 0.89" at 0 elev.
    if not RefrOn:
        return pAppEl, 0.0
    elif pAppEl > 0:
        ref = 1/math.tan(DTOR*(pAppEl + 7.31/(pAppEl + 4.4))) + 0.001351521673756295
        ref -= 0.06*math.sin((14.7*ref +13.)*DTOR) - 0.0134970632606319
        ref *= 283/(273 + pSiteRefTemp)
        ref *= pSiteRefPress/1010.0
        obsEl = pAppEl + ref/60.
        #print('El, ref (amin): ', obsEl, ref)
        return reduceDec(obsEl), ref*60.
    else:
        ref = 1/math.tan(DTOR*(7.31/(pAppEl + 4.4))) + 0.001351521673756295
        ref -= 0.06*math.sin((14.7*ref +13.)*DTOR) - 0.0134970632606319
        ref *= 283/(273 + pSiteRefTemp)
        ref *= pSiteRefPress/1010.0
        obsEl = pAppEl + ref/60.
        #print('El, ref: ', obsEl, ref)
        return reduceDec(obsEl), ref*60.

def correct_refraction_inEl(pObsEl, pSiteRefTemp, pSiteRefPress): #Deg, C. , mmHg
    if not RefrOn:
        return pObsEl, 0.0
    else:
        ERRORlimit = 0.01*STOR
        count = 0
        error = 10
        trial= pObsEl
        while abs(error) > ERRORlimit:
            appTrial, ref = apply_refraction_inEl(trial, pSiteRefTemp, pSiteRefPress)
            error = appTrial - pObsEl
            trial -= error
            count += 1
            if count > 25:   #count about 12 at-0.5 deg.  3 at 45deg.
                return reduceDec(pObsEl)
                print('correct_refraction_inEl()  FAILED!')
        #print('Count:  ', count)
        return reduceDec(trial), reduceDec(pObsEl - trial)*3600.

def test_refraction():   #passes 20170104   20180909
    for el in range(90, -1, -1):
        refEl, ref = apply_refraction_inEl(el, siteRefTemp, siteRefPress)
        resultEl, ref2 = correct_refraction_inEl(refEl, siteRefTemp, siteRefPress)
        print(el, refEl, resultEl, (el-resultEl)*DTOS, ref, ref2)

def appToObsRaHa(appRa, appDec, pSidTime):
    global raRefr, decRefr, refAsec
    appHa, appDec = transform_raDec_to_haDec(appRa, appDec, pSidTime)
    appAz, appAlt = transform_haDec_to_azAlt(appHa, appDec, siteLatitude)
    obsAlt, refAsec = apply_refraction_inEl(appAlt, siteRefTemp, siteRefPress)
    obsHa, obsDec = transform_azAlt_to_HaDec(appAz, obsAlt, siteLatitude)
    raRefr = reduceHa(appHa - obsHa)*HTOS
    decRefr = -reduceDec(appDec -obsDec)*DTOS
    return reduceHa(obsHa), reduceDec(obsDec), refAsec

def obsToAppHaRa(obsHa, obsDec, pSidTime):
    global raRefr, decRefr, refAsec
    obsAz, obsAlt = transform_haDec_to_azAlt(obsHa, obsDec, siteLatitude)
    appAlt, refr = correct_refraction_inEl(obsAlt, siteRefTemp, siteRefPress)
    appHa, appDec = transform_azAlt_to_HaDec(obsAz, appAlt, siteLatitude)
    appRa, appDec = transformHatoRaDec(appHa, appDec, pSidTime)
    raRefr = reduceHa(-appHa + obsHa)*HTOS
    decRefr = -reduceDec(-appDec + obsDec)*DTOS
    return reduceRa(appRa), reduceDec(appDec)

def appToObsRaRa(appRa, appDec, pSidTime):
    obsHa, obsDec, refR = appToObsRaHa(appRa, appDec, pSidTime)
    obsRa, obsDec = transformHatoRaDec(obsHa, obsDec, pSidTime)
    return reduceRa(obsRa), reduceDec(obsDec), refR

def obsToAppRaRa(obsRa, obsDec, pSidTime):
    obsHa, obsDec = transform_raDec_to_haDec(obsRa, obsDec, pSidTime)
    appRa, appDec, refr =  obsToAppHaRa(obsHa, obsDec, pSidTime)
    return reduceRa(appRa), reduceDec(appDec)


def test_app_obs_app():
    ra = [0, 5 ,4, 3, 2, 1, 0, 24, 23, 22, 21, 21, 20]
    dec =[0, -35, -20, -5, 0, 10, 25, siteLatitude, 40, 55, 70, 85, 89.999, 90]
    for pRa in ra:
        for pDec in dec:
            pHa, pDec = transform_raDec_to_haDec(pRa, pDec, 0)
            az, alt = transform_haDec_to_azAlt(pHa, pDec, 34)
            if alt > 0:
                oRa, oDec = appToObs(pRa, pDec, 0.0, 34)
                #print(pRa, oRa, pDec, oDec)
                aRa, aDec = obsToApp(oRa, oDec, 0.0, 34)
                #print(pRa, oRa, aRa, pDec, oDec, aDec, (pRa - aRa)*HTOS, (pDec - aDec)*DTOS)
                #print((pRa - aRa)*HTOS,( pDec - aDec)*DTOS)


def transform_mount_to_observed(pRoll, pPitch, pPierSide, loud=False):
    #I am amazed this works so well even very near the celestrial pole.
    if not ModelOn:
        return (pRoll, pPitch)
    else:
        cosDec = math.cos(pPitch*DTOR)
        ERRORlimit = 0.001*STOR
        count = 0
        error = 10
        rollTrial = pRoll
        pitchTrial = pPitch
        while abs(error) > ERRORlimit:
            obsRollTrial, obsPitchTrial = transformObsToMount(rollTrial, \
                          pitchTrial, pPierSide)
            errorRoll = reduceHa(obsRollTrial - pRoll)
            errorPitch = obsPitchTrial - pPitch
            error = math.sqrt(cosDec*(errorRoll*15)**2 + (errorPitch)**2)
            #if loud: print(count, errorRoll, errorPitch, error*DTOS)
            rollTrial -= errorRoll
            pitchTrial -= errorPitch
            count +=1
            if count > 500:   #count about 12 at-0.5 deg.  3 at 45deg.
                return pRoll, pPitch
                if loud: print('correct_mount_to_observedl()  FAILED!')
        return reduceRa(rollTrial), reduceDec(pitchTrial)


def transformObsToMount(pRoll, pPitch, pPierSide, loud=False):
    #This routine is diectly invertible.
    '''
    Long-run probably best way to do this in inherit a model dictionary.

    NBNBNB improbable minus sign of ID, WD

    #This implements a basic 7 term TPOINT transformation.

    '''
    global raCorr, decCorr, model



    if not ModelOn:
        return (pRoll, pPitch)
    else:
        ih = model['IH']
        idec = model['ID']
        Wh = model['WH']
        Wd = model['WD']
        ma = model['MA']
        me = model['ME']
        ch = model['CH']
        np = model['NP']
        tf = model['TF']
        tx = model['TX']
        hces = model['HCES']
        hcec = model['HCEC']
        dces = model['DCES']
        dcec = model['DCEC']
        ia = model['IA']
        ie = model['IE']
        an = model['AN']
        aw = model['AW']
        ca = model['CA']
        npae = model['NPAE']
        aces = model['ACES']
        acec = model['ACEC']
        eces = model['ECES']
        ecec = model['ECEC']
        #Apply IJ and ID to incoming coordinates, and if needed GEM correction.
        rRoll = math.radians(pRoll*15 - ih /3600.)
        rPitch = math.radians(pPitch - idec /3600.)
        if not ALTAZ:
            if pPierSide == 1:
                rRoll += math.radians(Wh/3600.)
                rPitch -= math.radians(Wd/3600.)  #NB Adjust signs to normal EWNS view
                #print("PIERSIDE IS BEING APPLIED:  ", pPierSide, Wh, Wd)
            if loud:
                print(ih, idec, Wh, Wd, ma, me, ch, np, tf, tx, hces, hcec, dces, dcec)

                # Do these need flipping?  I do not think so.
            ch = -ch/3600.
            np = -np/3600.
            #This is exact trigonometrically:
            if loud: print('Pre CN; roll, pitch:  ', rRoll*RTOH, rPitch*RTOD)
            cnRoll =  rRoll + math.atan2(math.cos(math.radians(np)) \
                            * math.tan(math.radians(ch)) \
                            + math.sin(math.radians(np))*math.sin(rPitch) \
                            , math.cos(rPitch))
            cnPitch=  math.asin(math.cos(math.radians(np)) \
                            * math.cos(math.radians(ch)) \
                            * math.sin(rPitch) - math.sin(math.radians(np)) \
                            * math.sin(math.radians(ch)))
            if loud:  print('Post CN; roll, pitch:  ', cnRoll*RTOH, cnPitch*RTOD)
            x, y, z = sphRect(math.degrees(cnRoll), math.degrees(cnPitch))
            if loud: print('To spherical:  ', x, y, z, x*x+y*y+z*z)
            #Apply MA error:
            if loud: print('Pre  MA:       ', x, y, z, math.radians(-ma/3600.))
            y, z = rotate(y, z, math.radians(-ma/3600.))#/math.cos(math.radians(siteLatitude)))
            if loud: print('Post MA:       ', x, y, z, x*x+y*y+z*z)
            #Apply ME error:
            x, z = rotate(x, z, math.radians(-me/3600.))
            if loud: print('Post ME:       ', x, y, z, x*x+y*y+z*z)
            #Apply latLtude
            x, z = rotate(x, z, math.radians(90.0 - siteLatitude))
            if loud: print('Post-Lat:  ', x, y, z, x*x+y*y+z*z)
            #Apply TF, TX
            az, el = rectSph(x, y, z)  #math.pi/2. -
            if loud: print('Az El:  ',  az+180., el)
            #flexure causes mount to sag so a shift in el, apply then
            #move back to other coordinate system
            zen = 90 - el
            if zen >= 89:
                clampedTz = 57.289961630759144  #tan(89)
            else:
                clampedTz = math.tan(math.radians(zen))
            defl= math.radians(tf/3600.)*math.sin(math.radians(zen)) + math.radians(tx/3600.)*clampedTz
            el += defl*RTOD
            if loud: print('Post Tf,Tx; az, el, z, defl:  ',  az+180., el, z*RTOD, defl*RTOS)
            #The above is dubious but close for small deflections.
            #Unapply Latitude

            x, y, z = sphRect(az , el)
            if loud: print('Back:  ', x, y, z, x*x+y*y+z*z)
            x,z = rotate(x, z, -math.radians(90.0 - siteLatitude))
            if loud: print('Back-Lat:  ', x, y, z, x*x+y*y+z*z)
            fRoll, fPitch = rectSph(x, y, z)
            if loud: print('Back-Sph:  ', fRoll*RTOH, fPitch*RTOD)
            cRoll = centration(fRoll, -hces, hcec)
            if loud: print('f,c Roll: ', fRoll, cRoll)
            cPitch = centration(fPitch, -dces, dcec)

            if loud: print('f, c Pitch: ', fPitch, cPitch)
            corrRoll = reduceRa(cRoll/15.)
            corrPitch = reduceDec(cPitch)
            if loud: print('Final:   ', fRoll*RTOH, fPitch*RTOD)
            raCorr = reduceHa(corrRoll - pRoll)*15*3600
            decCorr = reduceDec(corrPitch - pPitch)*3600
            if loud: print('Corrections:  ', raCorr, decCorr)
            return(corrRoll, corrPitch)
        elif ALTAZ:
            if loud:
                print(ih, idec, ia, ie, an, aw, tf, tx, ca, npae, aces, acec, eces, ecec)
            '''
            Convert Incoming Ha, Dec to Alt-Az system, apply corrections then
            convert back to equitorial.  At this stage we assume positioning  of
            the mounting is still done in Ra/Dec coordianates so the canonical
            velocites are generated by the mounting, not any Python level code.
            '''
            loud=False
            az, alt = transform_haDec_to_azAlt(pRoll, pPitch)
            rRoll = math.radians(az + ia /3600.)
            rPitch = math.radians(alt - ie /3600.)
            ch = ca/3600.
            np = npae/3600.
            #This is exact trigonometrically:
            if loud: print('Pre CANPAE; roll, pitch:  ', rRoll*RTOH, rPitch*RTOD)
            cnRoll =  rRoll + math.atan2(math.cos(math.radians(np)) \
                            * math.tan(math.radians(ch)) \
                            + math.sin(math.radians(np))*math.sin(rPitch) \
                            , math.cos(rPitch))
            cnPitch=  math.asin(math.cos(math.radians(np)) \
                            * math.cos(math.radians(ch)) \
                            * math.sin(rPitch) - math.sin(math.radians(np)) \
                            * math.sin(math.radians(ch)))
            if loud:  print('Post CANPAE; roll, pitch:  ', cnRoll*RTOH, cnPitch*RTOD)
            x, y, z = sphRect(math.degrees(cnRoll), math.degrees(cnPitch))
            if loud: print('To spherical:  ', x, y, z, x*x+y*y+z*z)
            #Apply AN error:
            if loud: print('Pre  AW:       ', x, y, z, math.radians(aw/3600.))
            y, z = rotate(y, z, math.radians(-aw/3600.))#/math.cos(math.radians(siteLatitude)))
            if loud: print('Post AW:       ', x, y, z, x*x+y*y+z*z)
            #Apply AW error:
            if loud: print('Pre  AN:       ', x, y, z, math.radians(an/3600.))
            x, z = rotate(x, z, math.radians(an/3600.))
            if loud: print('Post AN:       ', x, y, z, x*x+y*y+z*z)
#            #Apply latLtude
#            x, z = rotate(x, z, math.radians(90.0 - siteLatitude))
#            if loud: print('Post-Lat:  ', x, y, z, x*x+y*y+z*z)
            #Apply TF, TX
            az, el = rectSph(x, y, z)  #math.pi/2. -
            if loud: print('Az El:  ',  az+180., el)
            #flexure causes mount to sag so a shift in el, apply then
            #move back to other coordinate system
            zen = 90 - el
            if zen >= 89:
                clampedTz = 57.289961630759144  #tan(89)
            else:
                clampedTz = math.tan(math.radians(zen))
            defl= math.radians(tf/3600.)*math.sin(math.radians(zen)) + math.radians(tx/3600.)*clampedTz
            el += defl*RTOD
            if loud: print('Post Tf,Tx; az, el, z, defl:  ',  az+180., el, z*RTOD, defl*RTOS)
            #The above is dubious but close for small deflections.
            #Unapply Latitude

            x, y, z = sphRect(az , el)
            if loud: print('Back:  ', x, y, z, x*x+y*y+z*z)
#            x,z = rotate(x, z, -math.radians(90.0 - siteLatitude))
#            if loud: print('Back-Lat:  ', x, y, z, x*x+y*y+z*z)
            fRoll, fPitch = rectSph(x, y, z)
            if loud: print('Back-Sph:  ', fRoll*RTOH, fPitch*RTOD)
            cRoll = centration(fRoll, aces, acec)
            if loud: print('f,c Roll: ', fRoll, cRoll)
            cPitch = centration(fPitch, -eces, ecec)
            if loud: print('f, c Pitch: ', fPitch, cPitch)
            corrRoll = reduceAz(cRoll)
            corrPitch = reduceAlt(cPitch)
            if loud: print('Final Az, ALT:   ', corrRoll, corrPitch)
            haH, decD = transform_azAlt_to_HaDec(corrRoll, corrPitch)
            raCorr = reduceHa(haH - pRoll)*15*3600
            decCorr = reduceDec(decD - pPitch)*3600
            if loud: print('Corrections:  ', raCorr, decCorr)
            return(haH, decD)

def seedAltAzModel():
    global ALTAZ
    model['IH'] =0
    model['ID'] = 0
    model['WH'] = 0
    model['WD'] = 0
    model['MA'] = 0
    model['ME'] = 0
    model['CH'] = 0
    model['NP'] = 0
    model['TF'] = 70
    model['TX'] = -10
    model['HCES'] = 0
    model['HCEC'] = 0
    model['DCES'] = 0
    model['DCEC'] = 0
    model['IA'] = 100
    model['IE'] = -100
    model['AN'] = 30
    model['AW'] = -40
    model['CA'] = 50
    model['NPAE'] = 60
    model['ACES'] = 80
    model['ACEC'] = -90
    model['ECES'] = -85
    model['ECEC'] = 74
    ALTAZ = True
    test_misAlign()


def seedEquModel():
    global ALTAZ
    model['IH'] = 35
    model['ID'] = -30
    model['WH'] = 4
    model['WD'] = 0
    model['MA'] = 50
    model['ME'] =-70
    model['CH'] = 85
    model['NP'] = -40
    model['TF'] = 20
    model['TX'] = 5
    model['HCES'] = 100
    model['HCEC'] = -80
    model['DCES'] = 125
    model['DCEC'] = -45
    model['IA'] = 0
    model['IE'] = 0
    model['AN'] = 0
    model['AW'] = 0
    model['CA'] = 0
    model['NPAE'] = 0
    model['ACES'] = 0
    model['ACEC'] = 0
    model['ECES'] = 0
    model['ECEC'] = 0
    ALTAZ = False
    test_misAlign()

def getTpointModel(pDDmod=None):
    '''
    This fetches a model from TPOINT directory.  Note Toint does NOT produce
    EH ED.  This can be sorted by deciding if there is one model and an EH ED
    correction, or a model per flip side.  TPOINT can be set up to script
    those calculations.
    '''
    global model, modelChanged
    try:
        if pDDmod == None:
            pPath = 'C:\\Users\\User\\Dropbox\\PyWork\\PtrObserver\\PTR\\TPOINT\\ptr_mod.dat'
            WHP = 0.0
            WDP = 0.0
            print('Using ptr-Mod from TPOINT.')
        else:
            pPath = 'C:\\Users\\User\\Dropbox\\PyWork\\PtrObserver\\PTR\\TPOINT\\' + pDDmod + '.dat'
            #NOTE assumed a custom model deals with WHP
        modelf = open(pPath, 'r')
        print('Model: '+ pPath +'\n', modelf.readline(), modelf.readline())
        for line in modelf:
            if line != 'END' or len(line) > 7:
                print(line)
                items = line.split()
                try:
                    items[1] = float(items[1])
                    if abs(items[1]/float(items[2])) >= 2:  #reject low sigma terms
                        #store as needed.
                        if items[0] =='IH':
                            model['IH'] = items[1]
                        if items[0] =='ID':
                            model['ID'] = items[1]
                        if items[0] =='WH':
                            model['WH'] = items[1]
                        if items[0] =='WD':
                           model['WD'] = items[1]
                        if items[0] =='MA':
                            model['MA'] = items[1]
                        if items[0] =='ME':
                            model['ME'] = items[1]
                        if items[0] =='CH':
                            model['CH'] = items[1]
                        if items[0] =='NP':
                            model['NP'] = items[1]
                        if items[0] =='TF':
                            model['TF'] = items[1]
                        if items[0] =='TX':
                            model['TX']= items[1]
                        if items[0] =='HCES':
                            model['HCES'] = items[1]
                        if items[0] =='HCEC':
                            model['HCEC'] = items[1]
                        if items[0] =='DCES':
                            model['DCES'] = items[1]
                        if items[0] =='DCEC':
                            model['DCEC'] = items[1]
                        if items[0] =='IA':
                            model['IA'] = items[1]
                        if items[0] =='IE':
                            model['IE'] = items[1]
                        if items[0] =='AN':
                            model['AN'] = items[1]
                        if items[0] =='AW':
                            model['AW'] = items[1]
                        if items[0] =='CA':
                            model['CA'] = items[1]
                        if items[0] =='NPAE':
                            model['NPAE'] = items[1]
                        if items[0] =='ACES':
                            model['ACES'] = items[1]
                        if items[0] =='ACEC':
                            model['ACEC'] = items[1]
                        if items[0] =='ECES':
                            model['ECES'] = items[1]
                        if items[0] =='ECEC':
                            model['ECEC'] = items[1]
                except:
                    pass
        modelf.close()

    except:
        print('No model file found!  Please look elsewhere.')
    modelChanged = False


def writeTpointModel():
    global model, modelChanged
    pPath = 'C:\\Users\\User\\Dropbox\\PyWork\\PtrObserver\\PTR\\TPOINT\\ptr_mod.dat'
    modelf = open(pPath, 'w')
    modelf.write('0.18m AP Starfire on  AP-1600 \n')
    modelf.write('T  0  0.00    0.000   0.0000\n')
    modelf.write('     IH       ' + str(round(float(model['IH']), 2)) + '     3.0  \n')
    modelf.write('     ID       ' + str(round(float(model['ID']), 2)) + '     3.0  \n')
    modelf.write('     WH       ' + str(round(float(model['WH']), 2)) + '     3.0  \n')
    modelf.write('     WD       ' + str(round(float(model['WD']), 2)) + '     3.0  \n')
    modelf.write('     MA       ' + str(round(float(model['MA']), 2)) + '     3.0  \n')
    modelf.write('     ME       ' + str(round(float(model['ME']), 2)) + '     3.0  \n')
    modelf.write('     CH       ' + str(round(float(model['CH']), 2)) + '     3.0  \n')
    modelf.write('     NP       ' + str(round(float(model['NP']), 2)) + '     3.0  \n')
    modelf.write('     TF       ' + str(round(float(model['TF']), 2)) + '     3.0  \n')
    modelf.write('     TX       ' + str(round(float(model['TX']), 2)) + '     3.0  \n')
    modelf.write('     HCES     ' + str(round(float(model['HCES']), 2)) + '     3.0  \n')
    modelf.write('     HCEC     ' + str(round(float(model['HCEC']), 2)) + '     3.0  \n')
    modelf.write('     DCES     ' + str(round(float(model['DCES']), 2)) + '     3.0  \n')
    modelf.write('     DCEC     ' + str(round(float(model['DCEC']), 2)) + '     3.0  \n')
    modelf.write('     IA       ' + str(round(float(model['IA']), 2)) + '     3.0  \n')
    modelf.write('     IE       ' + str(round(float(model['IE']), 2)) + '     3.0  \n')
    modelf.write('     AN       ' + str(round(float(model['AN']), 2)) + '     3.0  \n')
    modelf.write('     AW       ' + str(round(float(model['AW']), 2)) + '     3.0  \n')
    modelf.write('     CA       ' + str(round(float(model['CA']), 2)) + '     3.0  \n')
    modelf.write('     NPAE     ' + str(round(float(model['NPAE']), 2)) + '     3.0  \n')
    modelf.write('     ACES     ' + str(round(float(model['ACES']), 2)) + '     3.0  \n')
    modelf.write('     ACEC     ' + str(round(float(model['ACEC']), 2)) + '     3.0  \n')
    modelf.write('     ECES     ' + str(round(float(model['ECES']), 2)) + '     3.0  \n')
    modelf.write('     ECEC     ' + str(round(float(model['ECEC']), 2)) + '     3.0  \n')
    modelf.write('END\n')
    modelf.close()


def getCorrs():
    global raCorr, decCorr, raRefr, decRefr, refAsec
    return (raCorr, decCorr, raRefr, decRefr, refAsec)

def getVels():
    global raVel, decVel
    return (raVel, decVel)

def setVels(pRaVel, pDecVel):
    global raVel, decVel
    raVel = pRaVel
    decVel = pDecVel

def centration (theta, a, b):
    theta = math.radians(theta)
    return math.degrees(math.atan2(math.sin(theta) - STOR*b, math.cos(theta) - STOR*a))

def test_misAlign():
    stars = open('C:\\Users\\obs\\Dropbox\\a_wer\\TPOINT\\perfct_ptr.dat', 'r')
    out = open('C:\\Users\\obs\\Dropbox\\a_wer\\TPOINT\\misalign.dat', 'w')
    for line in stars:
        if len(line) < 53:
            out.write(line)
            #print(line)
            continue
        entry = line[:]
        entry = entry.split()
        #print(entry)
        h = float(entry[0]) + (float(entry[1])/60. + float(entry[2])/3600.)
        d = float(entry[3][1:]) + (float(entry[4])/60. + float(entry[5])/3600.)
        sid = float(entry[12]) + float(entry[13])/60.
        if entry[3][0] == '-':
            d = -d
        ha = reduceHa(sid - h)
        iroll, npitch = transformObsToMount(ha, d, 0)
        nroll = reduceRa(sid - iroll)
        #print('misalign:  ', h, ha, d, nroll,iroll, npitch)

        mh, mm, ms = hToH_MStup(nroll)
        md, dm, ds = dToD_MStup(npitch)
        entry[6] = mh
        entry[7] = mm
        entry[8] = ms
        entry[9] = md
        entry[10] = dm
        entry[11] = ds
        #print('entry', entry)
        outStr = ''
        for field in range(len(entry)):
            outStr += entry[field] +"  "
        outStr = outStr[:-2]
        #NBNBNB Fix to copy over Sidtime and Aux variables.
        out.write(outStr +'\n' )
        #print(outStr+ '  00  00 \n')
    stars.close()
    out.close()


#20160316  Seems OK.
def transform_icrs_to_mount(pCoord, pCurrentPierSide, pLST=None, \
                            pRaDot=0.0, pDecDot=0.0, pName=None, nominalExp=0, \
                            loud=True, pTwoStep=False):

    if loud: print('transform_icrs_to_mount -- entered')

# =============================================================================
# NBNBNB This is not including proper motions so these coordinates are bad!
# NB raDot, etc., is for rapidly moving objects.
#
#    Temporarily remoinv any effect of rates and motions.
# =============================================================================
    pRaDot = 0
    pDecDot = 0
    meanCoord = SkyCoord(pCoord[0]*u.hour, pCoord[1]*u.degree, frame='icrs')
    t = meanCoord.transform_to(FK5(equinox=equinox_now))
    print('T:  ', t)
    appRa = fromHMS(str(t.ra.to_string(u.hour)))
    appDec = fromDMS(str(t.dec.to_string(u.degree)))
    print('Apparent:  ', hToHMS(appRa), toDMS(appDec))
    if loud: print('\n transform_icrs_to_mount:  \n J2000 to now:  ',  \
                   reduceHa(pCoord[0] - appRa)*HTOS, \
                   reduceDec(pCoord[1] - appDec)*DTOS, \
                   reduceHa(pCoord[0] - appRa)*HTOS/60, 'amin',
                   reduceDec(pCoord[1] - appDec)*DTOS/60, 'amin', '\n')
    nominalExp = abs(nominalExp)
    if nominalExp < 1:
        nominalExp = 1
    if pLST is not  None:
        lclSid = pLST
    else:
        lclSid =sidTime
    if loud: print('In:   sidTime, appRa, appDec, RaDot, DecDot:  ', lclSid, appRa, appDec, pRaDot, pDecDot, '\n')
    obsHa, obsDec, refDelta = appToObsRaHa(appRa, appDec, lclSid)
    if pTwoStep:
        obsHa -= 1
        print('TwoStep adjust made:  ', obsHa)
        if obsHa < WESTEASTLIMIT:
            obsHa = WESTEASTLIMIT-0.25

    if loud: print('appToObs: ha, dec, refDelta:  ', obsHa, obsDec, refDelta, '\n')
    roll, pitch = transformObsToMount(obsHa, obsDec, pCurrentPierSide)
    mountRa, mountDec = transformHatoRaDec(roll, pitch, lclSid)
    if loud: print('mount ra, dec, deltas:  ',  mountRa, mountDec, reduceHa(appRa - mountRa)*HTOS, reduceDec(appDec - mountDec)*DTOS, '\n')

    obsHa, obsDec, advRefDelta = appToObsRaHa(appRa, appDec, reduceRa(lclSid + nominalExp*SecTOH*APPTOSID))    #NBNBNB is apptosid correct?
    if loud: print('PRE: advToObs delta Ha, Dec, RefDelta  :  ',  obsHa, obsDec, advRefDelta, '\n')
    advRoll, advPitch = transformObsToMount(obsHa, obsDec, pCurrentPierSide)
    if loud: print('Post: advRoll advPitch  :  ',  advRoll, advPitch, '\n')
    advMountRa, advMountDec = transformHatoRaDec(advRoll, advPitch, lclSid)
    if loud:  print('Adv mount ra, dec, deltas:  ',  advMountRa, advMountDec, reduceHa(-appRa + advMountRa)*HTOS, reduceDec(-appDec + advMountDec)*DTOS, '\n')
    deltaRoll = (reduceHa(mountRa - advMountRa) )*HTOS/nominalExp - MOUNTRATE
    deltaPitch = -reduceDec(mountDec - advMountDec)*DTOS/nominalExp
    if loud: print('delta Roll, Pitch: asec/s ', deltaRoll, deltaPitch, '\n')
    slewAz, slewAlt = transform_haDec_to_azAlt(roll, mountDec) #roll is mount HA
    if loud: print('slewAzAlt:  ', slewAz, slewAlt)
    if loud: print('slew about to go to: ra/dec/az/alt.RatesOn ',  mountRa, mountDec, slewAz, slewAlt, RatesOn, '\n')
    if RatesOn:
        if loud:  print('Rates: asec/s ', float((pRaDot + deltaRoll)), float(pDecDot + deltaPitch), '\n')
    else:
        if loud:  print('Rates are off.')
    #retCoord = SkyCoord(mountRa*u.hour, mountDec*u.degree, frame='icrs')
    #icrsCoord = retCoord.transform_to(ICRS)
    #
    if loud:  print('Final: rah,decDeg, asec/s, asec/s', reduceRa(mountRa), reduceDec(mountDec),  float(pRaDot + deltaRoll), float(pDecDot + deltaPitch), '\n')
    return reduceRa(mountRa), reduceDec(mountDec),  float(pRaDot + deltaRoll), float(pDecDot + deltaPitch) #NBNBNB investigate AppptoSid conversion

#20160316 OK
def transform_mount_to_Icrs(pCoord, pCurrentPierSide, pLST=None, loud=False):

    if pLST is not None:
        lclSid = pLST
    else:
        lclSid =sidTime
    if loud: print('Pcoord:  ', pCoord)
    roll, pitch = transform_raDec_to_haDec(pCoord[0], pCoord[1], sidTime)
    if loud: print('MountToICRS1')
    obsHa, obsDec = transform_mount_to_observed(roll, pitch, pCurrentPierSide)
    if loud: print('MountToICRS2')
    appRa, appDec = obsToAppHaRa(obsHa, obsDec, sidTime)
    if loud: print('Out:  ', appRa, appDec, jYear)
    pCoordJnow = SkyCoord(appRa*u.hour, appDec*u.degree, frame='fk5', \
                          equinox=equinox_now)
    if loud: print('pCoord:  ', pCoordJnow)
    t = pCoordJnow.transform_to(ICRS)
    if loud: print('returning ICRS:  ', t)
    return (reduceRa(fromHMS(str(t.ra.to_string(u.hour)))),  \
            reduceDec(fromDMS(str(t.dec.to_string(u.degree)))))


def test_icrs_mount_icrs():
    ra = [11]#10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    dec = [0]#-40, -31, -20, -10, -5, 0, 10, 25, 40, 55, 70, 85, 88]
    for pRa in ra:
        for pDec in dec:
            for lst in [11 ]:#0.0001, 0, 24, 24.9999]:
                print('Starting:  ', pRa, pDec)
                Coord = (pRa,pDec)
                pierSide = 0
                toMount = transform_icrs_to_mount(Coord, pierSide, pLST=lst)
                print('ToMount:  ', toMount)

                back = transform_mount_to_Icrs(toMount, pierSide, pLST=lst)
                ra_err = reduceHa(back[0]-Coord[0])*HTOS
                dec_err = reduceDec(back[1]- Coord[1])*DTOS
                if abs(ra_err) > 0.1 or abs(dec_err) > 0.1:
                    print( pRa, pDec, lst, ra_err, dec_err)
                #print( pRa, pDec, lst, ra_err, dec_err)


def getwIHwID():
    #global IHP, IDP
    print('IH, ID:  ', model['IH'] ,  model['ID'] )
    return   model['IH'] ,  model['ID']

def incwIHwID(h, d):
    #global IHP, IDP
    model['IH']  += h
    model['ID']  += d
    modelChanged = True
    print("I's incremented")

def resetwIHwID():
    #global IHP, IDP
    model['IH']  = 0.0
    model['ID']  = 0.0
    modelChanged = True
    print("I's reset")
###Below is incorrect.



def geteCHeID():
    #global EHP, EDP, CHP
    print('EH, ED, CH:  ',  model['EH'] ,  model['ED'] ,  model['CH'] )
    return   model['CH'] ,  model['ED']

def inceCHeID(h, d):
    #global EHP, EDP, CHP
    model['EH']  -= h/2.
    model['ED']  += d
    model['CH']  += h
    modelChanged = True
    print("E's incremented")

def reseteCHeID():
    #global EHP, EDP, CHP
    model['EH']  = 0.0
    model['ED']  = 0.0
    model['CH'] = 0.0
    modelChanged = True
    print("E's reset")

ut_now, sid_now, equinox_now, day_of_year = get_current_times()
sidTime = round(sid_now.hour , 7)
print('Ut, Sid, Jnow:  ',  ut_now, sid_now, equinox_now)
press = 970*u.hPa
temp = 10*u.deg_C
hum = 0.5           #50%

print('Utility module loaded at: ', ephem.now(), round((ephem.now()), 4))
print('Local system Sidereal time is:  ', sidTime)
#SEQ_Counter = '000000'  #Should this be longer and persistently increasing?
if __name__ == '__main__':
    print('Welcome to the utility module.')


