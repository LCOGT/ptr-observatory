
"""
This is actually a sub-sub-process.
Each of the OSC colours needs to be SEParately SEP'ed so that
each can be astroaligned to their separate coloured smartstack image.
Say that three times fast.

This is called from SmartStackProcess.py when it is running an OSC stack.
As it is a relatively expensive (in time) operation, they need to run in parallel.
"""

import numpy as np
import sys
import pickle
import time
import bottleneck as bn
import sep
import traceback
from astropy.table import Table
from astropy.utils.exceptions import AstropyUserWarning
import warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)

input_sep_info=pickle.load(sys.stdin.buffer)
#input_jpeg_info=pickle.load(open('testseppickle','rb'))

print ("HERE IS THE INCOMING. ")
print (input_sep_info)

googtime=time.time()


hdufocusdata=input_sep_info[0]
pixscale=input_sep_info[1]
image_saturation_level= input_sep_info[2]
nativebin= input_sep_info[3]
readnoise= input_sep_info[4]
minimum_realistic_seeing= input_sep_info[5]
im_path=input_sep_info[6]
text_name=input_sep_info[7]
channel=input_sep_info[8]


# Really need to thresh the incoming image
googtime=time.time()
int_array_flattened=hdufocusdata.astype(int).ravel()
int_array_flattened=int_array_flattened[int_array_flattened > -10000]
unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
m=counts.argmax()
imageMode=unique[m]
print ("Calculating Mode: " +str(time.time()-googtime))

# Zerothreshing image
googtime=time.time()
histogramdata=np.column_stack([unique,counts]).astype(np.int32)
histogramdata[histogramdata[:,0] > -10000]
#Do some fiddle faddling to figure out the value that goes to zero less
zeroValueArray=histogramdata[histogramdata[:,0] < imageMode]
breaker=1
counter=0
while (breaker != 0):
    counter=counter+1
    if not (imageMode-counter) in zeroValueArray[:,0]:
        if not (imageMode-counter-1) in zeroValueArray[:,0]:
            if not (imageMode-counter-2) in zeroValueArray[:,0]:
                if not (imageMode-counter-3) in zeroValueArray[:,0]:
                    if not (imageMode-counter-4) in zeroValueArray[:,0]:
                        if not (imageMode-counter-5) in zeroValueArray[:,0]:
                            if not (imageMode-counter-6) in zeroValueArray[:,0]:
                                if not (imageMode-counter-7) in zeroValueArray[:,0]:
                                    if not (imageMode-counter-8) in zeroValueArray[:,0]:
                                        if not (imageMode-counter-9) in zeroValueArray[:,0]:
                                            if not (imageMode-counter-10) in zeroValueArray[:,0]:
                                                if not (imageMode-counter-11) in zeroValueArray[:,0]:
                                                    if not (imageMode-counter-12) in zeroValueArray[:,0]:
                                                        zeroValue=(imageMode-counter)
                                                        breaker =0

hdufocusdata[hdufocusdata < zeroValue] = np.nan

print ("Zero Threshing Image: " +str(time.time()-googtime))





# Check there are no nans in the image upon receipt
# This is necessary as nans aren't interpolated in the main thread.
# Fast next-door-neighbour in-fill algorithm
num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))
x_size=hdufocusdata.shape[0]
y_size=hdufocusdata.shape[1]
# this is actually faster than np.nanmean
#edgefillvalue=np.divide(bn.nansum(hdufocusdata),(x_size*y_size)-num_of_nans)
#breakpoint()
while num_of_nans > 0:
    # List the coordinates that are nan in the array
    nan_coords=np.argwhere(np.isnan(hdufocusdata))

    # For each coordinate try and find a non-nan-neighbour and steal its value
    for nancoord in nan_coords:
        x_nancoord=nancoord[0]
        y_nancoord=nancoord[1]
        done=False

        # Because edge pixels can tend to form in big clumps
        # Masking the array just with the mean at the edges
        # makes this MUCH faster to no visible effect for humans.
        # Also removes overscan
        if x_nancoord < 100:
            hdufocusdata[x_nancoord,y_nancoord]=imageMode
            done=True
        elif x_nancoord > (x_size-100):
            hdufocusdata[x_nancoord,y_nancoord]=imageMode

            done=True
        elif y_nancoord < 100:
            hdufocusdata[x_nancoord,y_nancoord]=imageMode

            done=True
        elif y_nancoord > (y_size-100):
            hdufocusdata[x_nancoord,y_nancoord]=imageMode
            done=True

        # left
        if not done:
            if x_nancoord != 0:
                value_here=hdufocusdata[x_nancoord-1,y_nancoord]
                if not np.isnan(value_here):
                    hdufocusdata[x_nancoord,y_nancoord]=value_here
                    done=True
        # right
        if not done:
            if x_nancoord != (x_size-1):
                value_here=hdufocusdata[x_nancoord+1,y_nancoord]
                if not np.isnan(value_here):
                    hdufocusdata[x_nancoord,y_nancoord]=value_here
                    done=True
        # below
        if not done:
            if y_nancoord != 0:
                value_here=hdufocusdata[x_nancoord,y_nancoord-1]
                if not np.isnan(value_here):
                    hdufocusdata[x_nancoord,y_nancoord]=value_here
                    done=True
        # above
        if not done:
            if y_nancoord != (y_size-1):
                value_here=hdufocusdata[x_nancoord,y_nancoord+1]
                if not np.isnan(value_here):
                    hdufocusdata[x_nancoord,y_nancoord]=value_here
                    done=True

    num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))






# https://stackoverflow.com/questions/9111711/get-coordinates-of-local-maxima-in-2d-array-above-certain-value
def localMax(a, include_diagonal=True, threshold=-np.inf) :
    # Pad array so we can handle edges
    ap = np.pad(a, ((1,1),(1,1)), constant_values=-np.inf )

    # Determines if each location is bigger than adjacent neighbors
    adjacentmax =(
    (ap[1:-1,1:-1] > threshold) &
    (ap[0:-2,1:-1] <= ap[1:-1,1:-1]) &
    (ap[2:,  1:-1] <= ap[1:-1,1:-1]) &
    (ap[1:-1,0:-2] <= ap[1:-1,1:-1]) &
    (ap[1:-1,2:  ] <= ap[1:-1,1:-1])
    )
    if not include_diagonal :
        return np.argwhere(adjacentmax)

    # Determines if each location is bigger than diagonal neighbors
    diagonalmax =(
    (ap[0:-2,0:-2] <= ap[1:-1,1:-1]) &
    (ap[2:  ,2:  ] <= ap[1:-1,1:-1]) &
    (ap[0:-2,2:  ] <= ap[1:-1,1:-1]) &
    (ap[2:  ,0:-2] <= ap[1:-1,1:-1])
    )

    return np.argwhere(adjacentmax & diagonalmax)



fx, fy = hdufocusdata.shape
#hdufocusdata[np.isnan(hdufocusdata)] = imageMode



#hdufocusdata=hdufocusdata-bn.nanmedian(hdufocusdata)
bkg = sep.Background(hdufocusdata, bw=32, bh=32, fw=3, fh=3)
bkg.subfrom(hdufocusdata)


tempstd=np.std(hdufocusdata)
threshold=3* np.std(hdufocusdata[hdufocusdata < (5*tempstd)])
list_of_local_maxima=localMax(hdufocusdata, threshold=threshold)
# Assess each point
pointvalues=np.zeros([len(list_of_local_maxima),3],dtype=float)
counter=0
for point in list_of_local_maxima:
    
    pointvalues[counter][0]=point[0]
    pointvalues[counter][1]=point[1]
    pointvalues[counter][2]=np.nan
    in_range=False
    if (point[0] > fx*0.1) and (point[1] > fy*0.1) and (point[0] < fx*0.9) and (point[1] < fy*0.9):
        in_range=True
    
    if in_range:                
        value_at_point=hdufocusdata[point[0],point[1]]
        try:
            value_at_neighbours=(hdufocusdata[point[0]-1,point[1]]+hdufocusdata[point[0]+1,point[1]]+hdufocusdata[point[0],point[1]-1]+hdufocusdata[point[0],point[1]+1])/4
        except:
            print(traceback.format_exc())
            breakpoint()
            
        # Check it isn't just a dot
        if value_at_neighbours < (0.6*value_at_point):
            #print ("BAH " + str(value_at_point) + " " + str(value_at_neighbours) )
            pointvalues[counter][2]=np.nan                       
        
        # If not saturated and far away from the edge
        elif value_at_point < 0.8*image_saturation_level:
            pointvalues[counter][2]=value_at_point
        
        else:
            pointvalues[counter][2]=np.nan
            
    counter=counter+1
    


# Trim list to remove things that have too many other things close to them.

# remove nan rows
pointvalues=pointvalues[~np.isnan(pointvalues).any(axis=1)]

# reverse sort by brightness
pointvalues=pointvalues[pointvalues[:,2].argsort()[::-1]]


# Keep top 200
if len(pointvalues) > 200:
    pointvalues=pointvalues[:200,:]


print ("Constructor " + str(time.time()-googtime))
sources = Table()
sources['x']=pointvalues[:,1]
sources['y']=pointvalues[:,0]


sources.write(im_path + text_name.replace('.txt', '.sep'), format='csv', overwrite=True)


pickle.dump(sources, open(im_path + 'oscaasep.pickle' + channel, 'wb'))


