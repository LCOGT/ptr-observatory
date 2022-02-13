# -*- coding: utf-8 -*-
"""
Created on Sun Jan 16 20:09:25 2022

@author: obs
"""

import math

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

def convert_to_mechanical_h_d(pRa, pDec, pFlip):
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

def rect_sph_d(pX, pY, pZ):
    rSq = pX*pX + pY*pY + pZ*pZ
    return math.degrees(math.atan2(pY, pX)), math.degrees(math.asin(pZ/rSq))

def sph_rect_d(pRoll, pPitch):
    pRoll = math.radians(pRoll)
    pPitch = math.radians(pPitch)
    cPitch = math.cos(pPitch)
    return math.cos(pRoll)*cPitch, math.sin(pRoll)*cPitch, math.sin(pPitch)

def rotate_r(pX, pY, pTheta):
    cTheta = math.cos(pTheta)
    sTheta = math.sin(pTheta)
    return pX * cTheta - pY * sTheta, pX * sTheta + pY * cTheta

def centration_d (theta, a, b):
    theta = math.radians(theta)
    return math.degrees(math.atan2(math.sin(theta) - STOR*b, math.cos(theta) - STOR*a))

def centration_r (theta, a, b):
    # = math.radians(theta)
    return (math.atan2(math.sin(theta) - STOR*b, math.cos(theta) - STOR*a))

def transform_raDec_to_haDec_r(pRa, pDec, pSidTime):

    return (reduce_ha_r(pSidTime - pRa), reduce_dec_r(pDec))

def transform_haDec_to_raDec_r(pHa, pDec, pSidTime):
    return (reduce_ra_r(pSidTime - pHa), reduce_dec_r(pDec))

def transform_haDec_to_azAlt_r(pLocal_hour_angle, pDec, latr):
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    decr = pDec
    sinDec = math.sin(decr)
    cosDec = math.cos(decr)
    mHar = pLocal_hour_angle
    sinHa = math.sin(mHar)
    cosHa = math.cos(mHar)
    altitude = math.asin(sinLat*sinDec + cosLat*cosDec*cosHa)
    y = sinHa
    x = cosHa*sinLat - math.tan(decr)*cosLat
    azimuth = math.atan2(y, x) + PI
    azimuth = reduce_az_r(azimuth)
    altitude = reduce_alt_r(altitude)
    return (azimuth, altitude)#, local_hour_angle)

def transform_azAlt_to_haDec_r(pAz, pAlt, latr):
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    alt = pAlt
    sinAlt = math.sin(alt)
    cosAlt = math.cos(alt)
    az = pAz - PI
    sinAz = math.sin(az)
    cosAz = math.cos(az)
    if abs(abs(alt) - PIOVER2) < 1.0*STOR:
        return (0.0, reduce_dec_r(latr))     #by convention azimuth points South at local zenith
    else:
        dec = math.asin(sinAlt*sinLat - cosAlt*cosAz*cosLat)
        ha = math.atan2(sinAz, (cosAz*sinLat + math.tan(alt)*cosLat))
        return (reduce_ha_r(ha), reduce_dec_r(dec))

def transform_azAlt_to_raDec_r(pAz, pAlt, pLatitude, pSidTime):
    ha, dec = transform_azAlt_to_haDec_r(pAz, pAlt, pLatitude)
    return transform_haDec_to_raDec_r(ha, dec, pSidTime)

def dome_adjust_rah_decd(hah, azd, dec, flip, lat, r, offe, offs ):  #Flip = 'east' implies tel looking East.
                                            #AP Park five is 'west'. offsets are neg for east and
                                            #south at Park five.
    #Define a point above an offset telescope. Roughly at radius of dome or 
    # somewhat beyond.  X plane points North, Y plane is West, Z is towards zenith.
    #Establish the rectangular coordinates of the pointing vector.                                           
    if flip == 'East':
        x = offs
        y = offe           #+ r*math.sin(math.radians(hah*15.))
        z = r
        print('x,y,z,ha,dec,flip:     ', x, y, z, hah,dec, flip)

    if flip == 'West':
        x = -offs
        y = -offe
        z = r
        print('x,y,z,ha,dec,flip:   ', x, y, z, hah,dec, flip)
        # #Next we rotate in the Y - Z plane based on the hour angle by supplying Y and Z
        # # to a standard routine implementing a rotation. X, y = rotate_r(pX, pY, pTheta)
        # # A East flip positive HA should cause y to get smaller and z to get lower.
        # y_ha, z_ha = rotate_r(y, z, math.radians(-hah*15))
        # print('W x,y_ha,z_ha:         ', x, y_ha, z_ha)


    # finally, the new coordinates are (x, y_ha, z_ha)
    #Now we rotate in the X - Z plane based on the declination of the object.  The
    # order of the two rotations does not matter, the the Declination angle needs
    # to be carefully calculated based on a azimuth and hemispheric location of the 
    # telescope
    if flip == 'East' and (90 <= azd <= 270):   # The telescope is pointing south. + (CCW)
                                     # Rotation is therefore latitude - declination.
        rot =(lat - dec)
        x_dec, z_dec = rotate_r(x, z, math.radians(rot))
        print('x_dec,y,z_dec,rot:   ', x_dec, y, z_dec,rot)
    
        #Next we rotate in the Y - Z plane based on the hour angle by supplying Y and Z
        # to a standard routine implementing a rotation. X, y = rotate_r(pX, pY, pTheta)
        # A East flip positive HA should cause y to get smaller and z to get lower.
        y_ha, z_dec_ha = rotate_r(y, z_dec, math.radians(-hah*15))
        print('E x-dec,y_ha,z_ha_dec:         ', x_dec, y_ha, z_dec_ha)
        #And finally convert to spherical coordinates
        az_deg, alt_deg = rect_sph_d(x_dec, y_ha, z_dec_ha)
        print("pre_az:      ", az_deg) 
        az_deg = -az_deg    
        if az_deg < 0:
            az_deg += 360
        if az_deg >= 360: 
            az_deg -= 360
        print("E Dome az:  ", az_deg) # , alt_deg)
    if flip == 'West' and (90 <= azd <= 270):   # The telescope is pointing south. + (CCW)
                                     # Rotation is therefore latitude - declination.
        breakpoint()
        rot =(lat - dec)
        x_dec, z_dec = rotate_r(x, z, math.radians(rot))
        print('x_dec,y,z_dec,rot:   ', x_dec, y, z_dec,rot)
    
        #Next we rotate in the Y - Z plane based on the hour angle by supplying Y and Z
        # to a standard routine implementing a rotation. X, y = rotate_r(pX, pY, pTheta)
        # A East flip positive HA should cause y to get smaller and z to get lower.
        y_ha, z_dec_ha = rotate_r(y, z_dec, math.radians(-hah*15))
        print('E x-dec,y_ha,z_ha_dec:         ', x_dec, y_ha, z_dec_ha)
        #And finally convert to spherical coordinates
        az_deg, alt_deg = rect_sph_d(x_dec, y_ha, z_dec_ha)
        print("pre_az:      ", az_deg) 
        az_deg =  360 - az_deg     
        if az_deg < 0:
            az_deg += 360
        if az_deg >= 360: 
            az_deg -= 360
        print("W Dome az:  ", az_deg) # , alt_deg)
    elif flip == 'East' and (270 < azd  or azd < 90):
        breakpoint()
        if abs(hah) < 6.5:  #The telescope is between the zenith and the pole.
            rot = -(dec - lat)
        else:
            rot = -(180 - lat - dec)
        x_dec, z_dec = rotate_r(x, z, math.radians(rot))
        print('x_dec,y,z_dec,rot:   ', x_dec, y, z_dec,rot)
    
        #Next we rotate in the Y - Z plane based on the hour angle by supplying Y and Z
        # to a standard routine implementing a rotation. X, y = rotate_r(pX, pY, pTheta)
        # A East flip positive HA should cause y to get smaller and z to get lower.
        y_ha, z_dec_ha = rotate_r(y, z_dec, math.radians(-hah*15))
        print('E x-dec,y_ha,z_ha_dec:         ', x_dec, y_ha, z_dec_ha)
        #And finally convert to spherical coordinates
        az_deg, alt_deg = rect_sph_d(x_dec, y_ha, z_dec_ha)
        print("pre_az:      ", az_deg) 
        az_deg = -az_deg    
        if az_deg < 0:
            az_deg += 360
        if az_deg >= 360: 
            az_deg -= 360
        print("E Dome az:  ", az_deg) # , alt_deg)
     
        



if __name__ == "__main__":
    #hHink of coordinate system as -Y is East looking to +Y = West with +N to the right and +Z is up
    #When flipped be careful to get thesigns correct for offe and offs
    # The Az bellow iddicates pointing South if 180 or North if 0. Not used for anything else.
    
    #                    ha   az    dec   flip    lat  r     oe      os
#East side tests
    # print("\nLook up at zenith, tel on east side")
    # dome_adjust_rah_decd(0.001, 180 , 34.45, 'East', 34.5, 80, -19.55, -8) #Look Up at zenith.  daz = 112.1 Plausible
    # print("\nLook up at zenith, tel on east side, THEN GO TO +5.5 HA")
    # dome_adjust_rah_decd(5.5, 180 , 34.45, 'East', 34.5, 80, -19.55, -8) #+5h from zenith.  daz = 262.1 Plausible, right of due West
    # print("\nLook up at zenith, tel on east side, THEN GO TO -5.5 HA")
    # dome_adjust_rah_decd(-5.5, 180 , 34.45, 'East', 34.5, 80, -19.55, -8) #-5h from zenith. CW is Up! daz = 96 Plausible,south of due east.
    # print("\nLook up at zenith, then go W 3h to dec -10")
    # dome_adjust_rah_decd(3, 180 , -10, 'East', 34.5, 80, -19.55, -8) #+001h from zenith. Pasically Park 4  daz = 262.1
    # print("\nLook up at zenith, then go E -3h to dec -10")
    # dome_adjust_rah_decd(-3, 180 , 10, 'East', 34.5, 80, -19.55, -8) #+001h from zenith. Pasically Park 4  daz = 262.1
    # print("\nLook up at zenith, then go s to +1 alt")
    # dome_adjust_rah_decd(0.001, 180 , -55, 'East', 34.5, 80, -19.55, -8) #+001h from zenith. Pasically Park 4  daz = 262.1
    # print("\nLook up at zenith, then go s to +1 alt, +3 hours")
    # dome_adjust_rah_decd(3, 180 , -55, 'East', 34.5, 80, -19.55, -8) #+001h from zenith. Pasically Park 4  daz = 262.1
    # print("\nLook up at zenith, then go s to dec = 0, 0.01 hours")
    # dome_adjust_rah_decd(0.01, 180 , 0, 'East', 34.5, 80, -19.55, -8) #+001h from zenith. Pasically Park 4  daz = 262.1
    # print("\nLook up at zenith, then go s to +1 alt, +3 hours")
    # dome_adjust_rah_decd(3, 180 , 0, 'East', 34.5, 80, -19.55, -8) #+001h from zenith. Pasically Park 4  daz = 262.1
    # print("\nLook up at zenith, then go s to dec = 0, +5.5 hours")
    # dome_adjust_rah_decd(5.5, 180 , 0, 'East', 34.5, 80, -19.55, -8)
#WEST SIDE Tests
    dome_adjust_rah_decd(0.001, 1, 35, 'East', 34.5, 70, -19.55, -8)
    print('\n')
   # dome_adjust_rah_decd(-5, 180, 0, 'West', 34.5, 70, -19.55, -8)

    