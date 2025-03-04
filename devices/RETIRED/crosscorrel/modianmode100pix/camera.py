"""
Created on Tue Apr 20 22:19:25 2021

@author: obs, wer, dhunt

"""

#import copy
import datetime
import os
#from auto_stretch.stretch import Stretch
import queue
#import math
import shelve
import time
import traceback
import ephem
import copy
import json
import random
from astropy import log
log.setLevel('ERROR')
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import SkyCoord, AltAz
from astropy.nddata import block_reduce
from astropy import units as u
import glob
import numpy as np
import bottleneck as bn
import win32com.client
import pickle
from astropy.stats import sigma_clip
import math
import sep
import threading
from scipy import optimize
from scipy.linalg import svd
from astropy.utils.exceptions import AstropyUserWarning
import warnings
import subprocess
warnings.simplefilter('ignore', category=AstropyUserWarning)
import matplotlib.pyplot as plt
import matplotlib as mpl
#%matplotlib inline
#mpl.use('inline')
#['GTK3Agg', 'GTK3Cairo', 'MacOSX', 'nbAgg', 'Qt4Agg', 'Qt4Cairo', 'Qt5Agg', 'Qt5Cairo', 'TkAgg', 'TkCairo', 'WebAgg', 'WX', 'WXAgg', 'WXCairo', 'agg', 'cairo', 'pdf', 'pgf', 'ps', 'svg', 'template']
import matplotlib.style as mplstyle
mplstyle.use('fast')
mpl.rcParams['path.simplify'] = True
mpl.rcParams['path.simplify_threshold'] = 1.0

warnings.simplefilter("ignore", category=RuntimeWarning)
from devices.darkslide import Darkslide
from PIL import Image, ImageDraw
from global_yard import g_dev
from ptr_utility import plog
from ctypes import *
from skimage.registration import phase_cross_correlation
from multiprocessing.pool import Pool,ThreadPool
from scipy._lib._util import getfullargspec_no_self as _getfullargspec
from scipy.stats import binned_statistic

def mid_stretch_jpeg(data):
    """
    This product is based on software from the PixInsight project, developed by
    Pleiades Astrophoto and its contributors (http://pixinsight.com/).

    And also Tim Beccue with a minor flourishing/speedup by Michael Fitzgerald.
    """
    target_bkg=0.25
    shadows_clip=-1.25

    """ Stretch the image.

    Args:
        data (np.array): the original image data array.

    Returns:
        np.array: the stretched image data
    """

    try:
        data = data / np.max(data)
    except:
        data = data    #NB this avoids div by 0 is image is a very flat bias


    """Return the average deviation from the median.

    Args:
        data (np.array): array of floats, presumably the image data
    """
    median = np.median(data.ravel())
    n = data.size
    avg_dev = np.sum( np.absolute(data-median) / n )
    c0 = np.clip(median + (shadows_clip * avg_dev), 0, 1)
    x= median - c0

    """Midtones Transfer Function

    MTF(m, x) = {
        0                for x == 0,
        1/2              for x == m,
        1                for x == 1,

        (m - 1)x
        --------------   otherwise.
        (2m - 1)x - m
    }

    See the section "Midtones Balance" from
    https://pixinsight.com/doc/tools/HistogramTransformation/HistogramTransformation.html

    Args:
        m (float): midtones balance parameter
                   a value below 0.5 darkens the midtones
                   a value above 0.5 lightens the midtones
        x (np.array): the data that we want to copy and transform.
    """
    shape = x.shape
    x = x.ravel()
    zeros = x==0
    halfs = x==target_bkg
    ones = x==1
    others = np.logical_xor((x==x), (zeros + halfs + ones))
    x[zeros] = 0
    x[halfs] = 0.5
    x[ones] = 1
    x[others] = (target_bkg - 1) * x[others] / ((((2 * target_bkg) - 1) * x[others]) - target_bkg)
    m= x.reshape(shape)

    stretch_params = {
        "c0": c0,
        #"c1": 1,
        "m": m
    }

    m = stretch_params["m"]
    c0 = stretch_params["c0"]
    above = data >= c0

    # Clip everything below the shadows clipping point
    data[data < c0] = 0
    # For the rest of the pixels: apply the midtones transfer function
    x=(data[above] - c0)/(1 - c0)

    """Midtones Transfer Function

    MTF(m, x) = {
        0                for x == 0,
        1/2              for x == m,
        1                for x == 1,

        (m - 1)x
        --------------   otherwise.
        (2m - 1)x - m
    }

    See the section "Midtones Balance" from
    https://pixinsight.com/doc/tools/HistogramTransformation/HistogramTransformation.html

    Args:
        m (float): midtones balance parameter
                   a value below 0.5 darkens the midtones
                   a value above 0.5 lightens the midtones
        x (np.array): the data that we want to copy and transform.
    """
    shape = x.shape
    x = x.ravel()
    zeros = x==0
    halfs = x==m
    ones = x==1
    others = np.logical_xor((x==x), (zeros + halfs + ones))
    x[zeros] = 0
    x[halfs] = 0.5
    x[ones] = 1
    x[others] = (m - 1) * x[others] / ((((2 * m) - 1) * x[others]) - m)
    data[above]= x.reshape(shape)

    return data

# Note this is a thread!
def write_raw_file_out(packet):

    (raw, raw_name, hdudata, hduheader, frame_type, current_icrs_ra, current_icrs_dec,altpath,altfolder) = packet

    #print ("RAW RECEIVED: " + str(raw_name) )


    # Make sure normal paths exist
    os.makedirs(
        g_dev['cam'].camera_path + g_dev["day"], exist_ok=True
    )
    os.makedirs(
        g_dev['cam'].camera_path + g_dev["day"] + "/raw/", exist_ok=True
    )
    os.makedirs(
        g_dev['cam'].camera_path + g_dev["day"] + "/reduced/", exist_ok=True
    )
    os.makedirs(
        g_dev['cam'].camera_path + g_dev["day"] + "/calib/", exist_ok=True)


    # Make  sure the alt paths exist
    if raw == 'raw_alt_path':
        os.makedirs(
            altpath + g_dev["day"], exist_ok=True
        )
        os.makedirs(
            altpath + g_dev["day"] + "/raw/", exist_ok=True
        )
        os.makedirs(
            altpath + g_dev["day"] + "/reduced/", exist_ok=True
        )
        os.makedirs(
            altpath + g_dev["day"] + "/calib/", exist_ok=True)

        # altfolder = self.config['temporary_local_alt_archive_to_hold_files_while_copying']
        # if not os.path.exists(self.config['temporary_local_alt_archive_to_hold_files_while_copying']):
        #     os.makedirs(self.config['temporary_local_alt_archive_to_hold_files_while_copying'] )



    hdu = fits.PrimaryHDU()
    hdu.data = hdudata
    hdu.header = hduheader
    hdu.header["DATE"] = (
        datetime.date.strftime(
            datetime.datetime.utcfromtimestamp(time.time()), "%Y-%m-%d"
        ),
        "Date FITS file was written",
    )
    # if raw == 'raw_alt_path':# or slow_process[0] == 'reduced_alt_path':
    #     #breakpoint()
    #     hdu.writeto( altfolder +'/' + raw_name.split('/')[-1].replace('EX00','EX00-'+hduheader['OBSTYPE']), overwrite=True, output_verify='silentfix'
    #     )  # Save full raw file locally
    #     #self.altarchive_queue.put((copy.deepcopy(altfolder +'/' + raw_name.split('/')[-1].replace('EX00','EX00-'+hduheader['OBSTYPE'])),copy.deepcopy(raw_name),time.time()), block=False)
    # else:
    #     hdu.writeto(
    #         raw_name.replace('EX00','EX00-'+hduheader['OBSTYPE']), overwrite=True, output_verify='silentfix'
    #     )  # Save full raw file locally

    #hdu.writeto( altfolder +'/' + raw_name.split('/')[-1].replace('EX00','EX00-'+hduheader['OBSTYPE']), overwrite=True, output_verify='silentfix')
    hdu.writeto( raw_name, overwrite=True, output_verify='silentfix')

    try:
        hdu.close()
    except:
        pass
    del hdu
    #     saver = 1

    # except Exception as e:
    #     plog("Failed to write raw file: ", e)
    #     plog(traceback.format_exc())
    #         # if "requested" in e and "written" in e:
    #         #     plog(check_download_cache())
    #         # plog(traceback.format_exc())
    #         # time.sleep(10)
    #         # saverretries = saverretries + 1

    #print ("RAW PROCESSED: " + str(raw_name) )

def gaussian(x, amplitude, mean, stddev):
    return amplitude * np.exp(-((x - mean) / 4 / stddev)**2)

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

"""
This device works on cameras and getting images and header info back to the obs queues.
"""
dgs = "°"

# This class is for QHY camera control
class Qcam:
    LOG_LINE_NUM = 0
    # Python constants
    STR_BUFFER_SIZE = 32

    QHYCCD_SUCCESS = 0
    QHYCCD_ERROR = 0xFFFFFFFF

    stream_single_mode = 0
    stream_live_mode = 1

    bit_depth_8 = 8
    bit_depth_16 = 16
    readmodenum=c_int32(2)
    CONTROL_BRIGHTNESS = c_int(0)
    CONTROL_GAIN = c_int(6)
    CONTROL_USBTRAFFIC = c_int(6)

    CONTROL_SPEED = c_int(6)
    CONTROL_OFFSET = c_int(7)
    CONTROL_EXPOSURE = c_int(8)
    CAM_GPS = c_int(36)
    CAM_HUMIDITY = c_int(62)    #WER added these two new attributes.
    CAM_PRESSURE = c_int(63)
    CONTROL_CURTEMP = c_int(14)  #(14)
    CONTROL_CURPWM = c_int(15)
    CONTROL_MANULPWM = c_int(16)
    CONTROL_CFWPORT = c_int(17)
    CONTROL_CFWSLOTSNUM = c_int(44)
    CONTROL_COOLER = c_int(18)

    camera_params = {}

    so = None

    def __init__(self, dll_path):


        self.so = windll.LoadLibrary(dll_path)

        self.so.GetQHYCCDParam.restype = c_double
        self.so.GetQHYCCDParam.argtypes = [c_void_p, c_int]
        self.so.IsQHYCCDControlAvailable.argtypes = [c_void_p, c_int]
        self.so.IsQHYCCDCFWPlugged.argtypes = [c_void_p]

        self.so.GetQHYCCDMemLength.restype = c_ulong
        self.so.OpenQHYCCD.restype = c_void_p
        self.so.CloseQHYCCD.restype = c_void_p
        self.so.CloseQHYCCD.argtypes = [c_void_p]
        # self.so.EnableQHYCCDMessage(c_bool(False))
        self.so.EnableQHYCCDMessage(c_bool(True))
        self.so.SetQHYCCDStreamMode.argtypes = [c_void_p, c_uint8]
        self.so.InitQHYCCD.argtypes = [c_void_p]
        self.so.ExpQHYCCDSingleFrame.argtypes = [c_void_p]
        self.so.GetQHYCCDMemLength.argtypes = [c_void_p]
        self.so.BeginQHYCCDLive.argtypes = [c_void_p]
        self.so.SetQHYCCDResolution.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32, c_uint32]
        self.so.GetQHYCCDSingleFrame.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.GetQHYCCDChipInfo.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.GetQHYCCDLiveFrame.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.SetQHYCCDParam.argtypes = [c_void_p, c_int, c_double]
        self.so.SetQHYCCDBitsMode.argtypes = [c_void_p, c_uint32]

        #self.so.CancelQHYCCDExposingAndReadout.restype = c_int64
        self.so.CancelQHYCCDExposingAndReadout.argtypes = [c_int64]

        # self.so.GetQHYCCDNumberOfReadModes.restype = c_uint32
        # self.so.GetQHYCCDNumberOfReadModes.argtypes = [c_void_p, c_void_p]
        # self.so.GetQHYCCDReadModeName.argtypes = [c_void_p, c_uint32, c_char_p]
        # self.so.GetQHYCCDReadModeName.argtypes = [c_void_p, c_uint32]
        #self.so.GetQHYCCDReadMode.argtypes = [c_void_p,c_uint32]
        self.so.GetReadModesNumber.argtypes = [c_char_p, c_void_p]
        self.so.GetReadModeName.argtypes = [c_char_p, c_uint32, c_char_p]
        self.so.SetQHYCCDReadMode.argtypes = [c_void_p, c_uint32]

    @staticmethod
    def slot_index_to_param(val_slot_index):
        val_slot_index = val_slot_index + 48
        return val_slot_index

    @staticmethod
    def slot_value_to_index(val_slot_value):
        if val_slot_value == 78:
            return -1
        return val_slot_value - 48


@CFUNCTYPE(None, c_char_p)
def pnp_in(cam_id):

    plog("QHY Direct connect to camera: %s" % cam_id.decode('utf-8'))
    global qhycam_id
    qhycam_id=cam_id
    init_camera_param(qhycam_id)
    qhycam.camera_params[qhycam_id]['connect_to_pc'] = True


@CFUNCTYPE(None, c_char_p)
def pnp_out(cam_id):
    print("cam   - %s" % cam_id.decode('utf-8'))

# MTF - THIS IS A QHY FUNCTION THAT I HAVEN"T FIGURED OUT WHETHER IT IS MISSION CRITICAL OR NOT
def init_camera_param(cam_id):
    if not qhycam.camera_params.keys().__contains__(cam_id):
        qhycam.camera_params[cam_id] = {'connect_to_pc': False,
                                     'connect_to_sdk': False,
                                     'EXPOSURE': c_double(1000.0 * 1000.0),
                                     #'GAIN': c_double(54.0),
                                     'GAIN': c_double(54.0),
                                     'CONTROL_BRIGHTNESS': c_int(0),
                                     #'CONTROL_GAIN': c_int(6),
                                     'CONTROL_GAIN': c_int(6),
                                     #'CONTROL_USBTRAFFIC': c_int(6),
                                     'CONTROL_SPEED': c_int(6), ######
                                     'CONTROL_USBTRAFFIC': c_int(6),
                                     'CONTROL_EXPOSURE': c_int(8),
                                     #'CONTROL_CURTEMP': c_int(14),
                                     'CONTROL_CURTEMP': c_double(14),
                                     'CONTROL_CURPWM': c_int(15),
                                     'CONTROL_MANULPWM': c_int(16),
                                     'CONTROL_COOLER': c_int(18),
                                     'chip_width': c_double(),
                                     'chip_height': c_double(),
                                     'image_width': c_uint32(),
                                     'image_height': c_uint32(),
                                     'pixel_width': c_double(),
                                     'pixel_height': c_double(),
                                     'bits_per_pixel': c_uint32(),
                                     'mem_len': c_ulong(),
                                     'stream_mode': c_uint8(0),
                                     #'read_mode': c_uint8(0),
                                     'channels': c_uint32(),
                                     'read_mode_number': c_uint32(g_dev['obs'].config["camera"]["camera_1_1"]["settings"]['direct_qhy_readout_mode']),
                                     'read_mode_index': c_uint32(g_dev['obs'].config["camera"]["camera_1_1"]["settings"]['direct_qhy_readout_mode']),
                                     'read_mode_name': c_char('-'.encode('utf-8')),
                                     'prev_img_data': c_void_p(0),
                                     'prev_img': None,
                                     'handle': None,
                                     }



def next_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(g_dev['obs'].obsid_path + "ptr_night_shelf/" + pCamera + str(g_dev['obs'].name))
    sKey = "Sequence"
    try:
        seq = camShelf[sKey]  # get an 8 character string
    except:
        plog ("Failed to get seq key, starting from zero again")
        seq=1
    seqInt = int(seq)
    seqInt += 1
    seq = ("0000000000" + str(seqInt))[-8:]
    camShelf["Sequence"] = seq
    camShelf.close()
    SEQ_Counter = seq
    return seq

def test_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(g_dev['obs'].obsid_path + "ptr_night_shelf/" + pCamera + str(g_dev['obs'].name))
    sKey = "Sequence"
    seq = camShelf[sKey]  # get an 8 character string
    camShelf.close()
    SEQ_Counter = seq
    return seq


def reset_sequence(pCamera):
    try:
        camShelf = shelve.open(
            g_dev['obs'].obsid_path + "ptr_night_shelf/" + str(pCamera) + str(g_dev['obs'].name)
        )
        seqInt = int(-1)
        seqInt += 1
        seq = ("0000000000" + str(seqInt))[-8:]
        plog("Making new seq: ", pCamera, seq)
        camShelf["Sequence"] = seq
        camShelf.close()
        return seq
    except:
        plog("Nothing on the cam shelf in reset_sequence")
        return None

# # THIS IS A SCIPY FUNCTION LIBERATED INTO THIS CODE FOR SPEED TESTS
# def _lightweight_memoizer(f):
#     # very shallow memoization to address gh-13670: only remember the first set
#     # of parameters and corresponding function value, and only attempt to use
#     # them twice (the number of times the function is evaluated at x0).
#     def _memoized_func(params):
#         if _memoized_func.skip_lookup:
#             return f(params)

#         if np.all(_memoized_func.last_params == params):
#             return _memoized_func.last_val
#         elif _memoized_func.last_params is not None:
#             _memoized_func.skip_lookup = True

#         val = f(params)

#         if _memoized_func.last_params is None:
#             _memoized_func.last_params = np.copy(params)
#             _memoized_func.last_val = val

#         return val

#     _memoized_func.last_params = None
#     _memoized_func.last_val = None
#     _memoized_func.skip_lookup = False
#     return _memoized_func


# # THIS IS A SCIPY FUNCTION LIBERATED INTO THIS CODE FOR SPEED TESTS
# def _asarray_validated(a, check_finite=True,
#                        sparse_ok=False, objects_ok=False, mask_ok=False,
#                        as_inexact=False):
#     """
#     Helper function for SciPy argument validation.

#     Many SciPy linear algebra functions do support arbitrary array-like
#     input arguments. Examples of commonly unsupported inputs include
#     matrices containing inf/nan, sparse matrix representations, and
#     matrices with complicated elements.

#     Parameters
#     ----------
#     a : array_like
#         The array-like input.
#     check_finite : bool, optional
#         Whether to check that the input matrices contain only finite numbers.
#         Disabling may give a performance gain, but may result in problems
#         (crashes, non-termination) if the inputs do contain infinities or NaNs.
#         Default: True
#     sparse_ok : bool, optional
#         True if scipy sparse matrices are allowed.
#     objects_ok : bool, optional
#         True if arrays with dype('O') are allowed.
#     mask_ok : bool, optional
#         True if masked arrays are allowed.
#     as_inexact : bool, optional
#         True to convert the input array to a np.inexact dtype.

#     Returns
#     -------
#     ret : ndarray
#         The converted validated array.

#     """
#     if not sparse_ok:
#         import scipy.sparse
#         if scipy.sparse.issparse(a):
#             msg = ('Sparse matrices are not supported by this function. '
#                    'Perhaps one of the scipy.sparse.linalg functions '
#                    'would work instead.')
#             raise ValueError(msg)
#     if not mask_ok:
#         if np.ma.isMaskedArray(a):
#             raise ValueError('masked arrays are not supported')
#     toarray = np.asarray_chkfinite if check_finite else np.asarray
#     a = toarray(a)
#     if not objects_ok:
#         if a.dtype is np.dtype('O'):
#             raise ValueError('object arrays are not supported')
#     if as_inexact:
#         if not np.issubdtype(a.dtype, np.inexact):
#             a = toarray(a, dtype=np.float64)
#     return a

# # THIS IS A SCIPY FUNCTION LIBERATED INTO THIS CODE FOR SPEED TESTS
# def solve_triangular(a, b, trans=0, lower=False, unit_diagonal=False,
#                      overwrite_b=False, check_finite=True):
#     """
#     Solve the equation `a x = b` for `x`, assuming a is a triangular matrix.

#     Parameters
#     ----------
#     a : (M, M) array_like
#         A triangular matrix
#     b : (M,) or (M, N) array_like
#         Right-hand side matrix in `a x = b`
#     lower : bool, optional
#         Use only data contained in the lower triangle of `a`.
#         Default is to use upper triangle.
#     trans : {0, 1, 2, 'N', 'T', 'C'}, optional
#         Type of system to solve:

#         ========  =========
#         trans     system
#         ========  =========
#         0 or 'N'  a x  = b
#         1 or 'T'  a^T x = b
#         2 or 'C'  a^H x = b
#         ========  =========
#     unit_diagonal : bool, optional
#         If True, diagonal elements of `a` are assumed to be 1 and
#         will not be referenced.
#     overwrite_b : bool, optional
#         Allow overwriting data in `b` (may enhance performance)
#     check_finite : bool, optional
#         Whether to check that the input matrices contain only finite numbers.
#         Disabling may give a performance gain, but may result in problems
#         (crashes, non-termination) if the inputs do contain infinities or NaNs.

#     Returns
#     -------
#     x : (M,) or (M, N) ndarray
#         Solution to the system `a x = b`.  Shape of return matches `b`.

#     Raises
#     ------
#     LinAlgError
#         If `a` is singular

#     Notes
#     -----
#     .. versionadded:: 0.9.0

#     Examples
#     --------
#     Solve the lower triangular system a x = b, where::

#              [3  0  0  0]       [4]
#         a =  [2  1  0  0]   b = [2]
#              [1  0  1  0]       [4]
#              [1  1  1  1]       [2]

#     >>> import numpy as np
#     >>> from scipy.linalg import solve_triangular
#     >>> a = np.array([[3, 0, 0, 0], [2, 1, 0, 0], [1, 0, 1, 0], [1, 1, 1, 1]])
#     >>> b = np.array([4, 2, 4, 2])
#     >>> x = solve_triangular(a, b, lower=True)
#     >>> x
#     array([ 1.33333333, -0.66666667,  2.66666667, -1.33333333])
#     >>> a.dot(x)  # Check the result
#     array([ 4.,  2.,  4.,  2.])

#     """

#     # a1 = _asarray_validated(a, check_finite=check_finite)
#     # b1 = _asarray_validated(b, check_finite=check_finite)

#     # if len(a1.shape) != 2 or a1.shape[0] != a1.shape[1]:
#     #     raise ValueError('expected square matrix')
#     # if a1.shape[0] != b1.shape[0]:
#     #     raise ValueError(f'shapes of a {a1.shape} and b {b1.shape} are incompatible')
#     # overwrite_b = overwrite_b or _datacopied(b1, b)

#     # if len(a1.shape) != 2 or a1.shape[0] != a1.shape[1]:
#     #     raise ValueError('expected square matrix')
#     # if a1.shape[0] != b1.shape[0]:
#     #     raise ValueError(f'shapes of a {a1.shape} and b {b1.shape} are incompatible')
#     overwrite_b = overwrite_b or _datacopied(b1, b)


#     trans = {'N': 0, 'T': 1, 'C': 2}.get(trans, trans)
#     trtrs, = get_lapack_funcs(('trtrs',), (a1, b1))
#     if a1.flags.f_contiguous or trans == 2:
#         x, info = trtrs(a1, b1, overwrite_b=overwrite_b, lower=lower,
#                         trans=trans, unitdiag=unit_diagonal)
#     else:
#         # transposed system is solved since trtrs expects Fortran ordering
#         x, info = trtrs(a1.T, b1, overwrite_b=overwrite_b, lower=not lower,
#                         trans=not trans, unitdiag=unit_diagonal)

#     if info == 0:
#         return x
#     # if info > 0:
#     #     raise LinAlgError("singular matrix: resolution failed at diagonal %d" %
#     #                       (info-1))
#     # raise ValueError('illegal value in %dth argument of internal trtrs' %
#     #                  (-info))

# # THIS IS A SCIPY FUNCTION LIBERATED INTO THIS CODE FOR SPEED TESTS
# def _wrap_func(func, xdata, ydata, transform):
#     if transform is None:
#         def func_wrapped(params):
#             return func(xdata, *params) - ydata
#     elif transform.size == 1 or transform.ndim == 1:
#         def func_wrapped(params):
#             return transform * (func(xdata, *params) - ydata)
#     else:
#         # Chisq = (y - yd)^T C^{-1} (y-yd)
#         # transform = L such that C = L L^T
#         # C^{-1} = L^{-T} L^{-1}
#         # Chisq = (y - yd)^T L^{-T} L^{-1} (y-yd)
#         # Define (y-yd)' = L^{-1} (y-yd)
#         # by solving
#         # L (y-yd)' = (y-yd)
#         # and minimize (y-yd)'^T (y-yd)'
#         def func_wrapped(params):
#             return solve_triangular(transform, func(xdata, *params) - ydata, lower=True)
#     return func_wrapped


# def nonscipy_gaussian_curve_fit(f, xdata, ydata, p0=None, sigma=None, absolute_sigma=False,
#               check_finite=None, bounds=(-np.inf, np.inf), method=None,
#               jac=None, *, full_output=False, nan_policy=None,
#               **kwargs):
#     """
#     THIS IS MTF STRIPPING THE SCIPY CURVE_FIT FUNCTION TO BARE BONES.

#     Use non-linear least squares to fit a function, f, to data.

#     Assumes ``ydata = f(xdata, *params) + eps``.


#     """
#     # if p0 is None:
#     #     # determine number of parameters by inspecting the function
#     #     sig = _getfullargspec(f)
#     #     args = sig.args
#     #     if len(args) < 2:
#     #         raise ValueError("Unable to determine number of fit parameters.")
#     #     n = len(args) - 1
#     # else:
#     #p0 = np.atleast_1d(p0)
#     n = p0.size

#     print ("p0 is " + str(p0))
#     print ("n is " + str(n))

#     #if isinstance(bounds, Bounds):
#     #lb, ub = bounds.lb, bounds.ub
#     lb, ub = bounds
#     # else:
#     #     lb, ub = prepare_bounds(bounds, n)
#     # if p0 is None:
#     #     p0 = _initialize_feasible(lb, ub)

#     # bounded_problem = np.any((lb > -np.inf) | (ub < np.inf))
#     # if method is None:
#     #     if bounded_problem:
#     method = 'trf'
#         # else:
#         #     method = 'lm'

#     # if method == 'lm' and bounded_problem:
#     #     raise ValueError("Method 'lm' only works for unconstrained problems. "
#     #                      "Use 'trf' or 'dogbox' instead.")

#     # if check_finite is None:
#     #     check_finite = True if nan_policy is None else False

#     # # optimization may produce garbage for float32 inputs, cast them to float64
#     # if check_finite:
#     #     ydata = np.asarray_chkfinite(ydata, float)
#     # else:
#     #     ydata = np.asarray(ydata, float)

#     # if isinstance(xdata, (list, tuple, np.ndarray)):
#     #     # `xdata` is passed straight to the user-defined `f`, so allow
#     #     # non-array_like `xdata`.
#     #     if check_finite:
#     #         xdata = np.asarray_chkfinite(xdata, float)
#     #     else:
#     #         xdata = np.asarray(xdata, float)

#     # if ydata.size == 0:
#     #     raise ValueError("`ydata` must not be empty!")

#     # # nan handling is needed only if check_finite is False because if True,
#     # # the x-y data are already checked, and they don't contain nans.
#     # if not check_finite and nan_policy is not None:
#     #     if nan_policy == "propagate":
#     #         raise ValueError("`nan_policy='propagate'` is not supported "
#     #                          "by this function.")

#     #     policies = [None, 'raise', 'omit']
#     #     x_contains_nan, nan_policy = _contains_nan(xdata, nan_policy,
#     #                                                policies=policies)
#     #     y_contains_nan, nan_policy = _contains_nan(ydata, nan_policy,
#     #                                                policies=policies)

#     #     if (x_contains_nan or y_contains_nan) and nan_policy == 'omit':
#     #         # ignore NaNs for N dimensional arrays
#     #         has_nan = np.isnan(xdata)
#     #         has_nan = has_nan.any(axis=tuple(range(has_nan.ndim-1)))
#     #         has_nan |= np.isnan(ydata)

#     #         xdata = xdata[..., ~has_nan]
#     #         ydata = ydata[~has_nan]

#     # Determine type of sigma
#     # if sigma is not None:
#     #     sigma = np.asarray(sigma)

#     #     # if 1-D or a scalar, sigma are errors, define transform = 1/sigma
#     #     if sigma.size == 1 or sigma.shape == (ydata.size, ):
#     #         transform = 1.0 / sigma
#     #     # if 2-D, sigma is the covariance matrix,
#     #     # define transform = L such that L L^T = C
#     #     elif sigma.shape == (ydata.size, ydata.size):
#     #         try:
#     #             # scipy.linalg.cholesky requires lower=True to return L L^T = A
#     #             transform = cholesky(sigma, lower=True)
#     #         except LinAlgError as e:
#     #             raise ValueError("`sigma` must be positive definite.") from e
#     #     else:
#     #         raise ValueError("`sigma` has incorrect shape.")
#     # else:
#     transform = None

#     func = _lightweight_memoizer(_wrap_func(f, xdata, ydata, transform))

#     # if callable(jac):
#     #     jac = _lightweight_memoizer(_wrap_jac(jac, xdata, transform))
#     # elif jac is None and method != 'lm':
#     #     jac = '2-point'
#     jac = '2-point'
#     # if 'args' in kwargs:
#     #     # The specification for the model function `f` does not support
#     #     # additional arguments. Refer to the `curve_fit` docstring for
#     #     # acceptable call signatures of `f`.
#     #     raise ValueError("'args' is not a supported keyword argument.")

#     # if method == 'lm':
#     #     # if ydata.size == 1, this might be used for broadcast.
#     #     if ydata.size != 1 and n > ydata.size:
#     #         raise TypeError(f"The number of func parameters={n} must not"
#     #                         f" exceed the number of data points={ydata.size}")
#     #     res = leastsq(func, p0, Dfun=jac, full_output=1, **kwargs)
#     #     popt, pcov, infodict, errmsg, ier = res
#     #     ysize = len(infodict['fvec'])
#     #     cost = np.sum(infodict['fvec'] ** 2)
#     #     if ier not in [1, 2, 3, 4]:
#     #         raise RuntimeError("Optimal parameters not found: " + errmsg)
#     # else:

#     # Rename maxfev (leastsq) to max_nfev (least_squares), if specified.
#     # if 'max_nfev' not in kwargs:
#     #     kwargs['max_nfev'] = kwargs.pop('maxfev', None)
#     kwargs['max_nfev'] = None
#     res = optimize._lsq.least_squares(func, p0, jac=jac, bounds=bounds, method=method,
#                         **kwargs)

#     if not res.success:
#         raise RuntimeError("Optimal parameters not found: " + res.message)

#     infodict = dict(nfev=res.nfev, fvec=res.fun)
#     ier = res.status
#     errmsg = res.message

#     ysize = len(res.fun)
#     cost = 2 * res.cost  # res.cost is half sum of squares!
#     popt = res.x

#     # Do Moore-Penrose inverse discarding zero singular values.
#     _, s, VT = svd(res.jac, full_matrices=False)
#     threshold = np.finfo(float).eps * max(res.jac.shape) * s[0]
#     s = s[s > threshold]
#     VT = VT[:s.size]
#     pcov = np.dot(VT.T / s**2, VT)

#     warn_cov = False
#     if pcov is None or np.isnan(pcov).any():
#         # indeterminate covariance
#         pcov = np.zeros((len(popt), len(popt)), dtype=float)
#         pcov.fill(np.inf)
#         warn_cov = True
#     elif not absolute_sigma:
#         if ysize > p0.size:
#             s_sq = cost / (ysize - p0.size)
#             pcov = pcov * s_sq
#         else:
#             pcov.fill(np.inf)
#             warn_cov = True

#     if warn_cov:
#         plog('Covariance of the parameters could not be estimated')
#         # warnings.warn('Covariance of the parameters could not be estimated',
#         #               category=OptimizeWarning, stacklevel=2)

#     if full_output:
#         return popt, pcov, infodict, errmsg, ier
#     else:
        # return popt, pcov

def multiprocess_fast_gaussian_photometry(package):
    try:

        (cvalue, cx, cy, radprofile ,pixscale) = package

        # Reduce data down to make faster solvinging
        upperbin=math.floor(max(radprofile[:,0]))
        lowerbin=math.ceil(min(radprofile[:,0]))
        # Only need a quarter of an arcsecond bin.
        if np.isnan(pixscale) or pixscale == None:
            arcsecond_length_radial_profile = (upperbin-lowerbin)*8
        else:
            arcsecond_length_radial_profile = (upperbin-lowerbin)*pixscale
        number_of_bins=int(arcsecond_length_radial_profile/0.25)

        s, edges, _ = binned_statistic(radprofile[:,0],radprofile[:,1], statistic='mean', bins=np.linspace(lowerbin,upperbin,number_of_bins))

        max_value=np.nanmax(s)
        min_value=np.nanmin(s)

        threshold_value=(0.05*(max_value-min_value)) + min_value

        actualprofile=[]
        for q in range(len(s)):
            if not np.isnan(s[q]):
                if s[q] > threshold_value:
                    actualprofile.append([(edges[q]+edges[q+1])/2,s[q]])

        actualprofile=np.asarray(actualprofile)

        # Don't consider things that are clearly not stars but extended objects or blended stars).
        edgevalue_left=actualprofile[0][1]
        edgevalue_right=actualprofile[-1][1]

        if edgevalue_left < 0.6*cvalue and  edgevalue_right < 0.6*cvalue:


            # Different faster fitter to consider
            peak_value_index=np.argmax(actualprofile[:,1])
            peak_value=actualprofile[peak_value_index][1]

            # Get the mean of the 5 pixels around the max
            # and use the mean of those values and the peak value
            # to use as the amplitude
            temp_amplitude=actualprofile[peak_value_index-2][1]+actualprofile[peak_value_index-1][1]+actualprofile[peak_value_index][1]+actualprofile[peak_value_index+1][1]+actualprofile[peak_value_index+2][1]
            temp_amplitude=temp_amplitude/5
            # Check that the mean of the temp_amplitude here is at least 0.6 * cvalue

            if temp_amplitude > 0.5*peak_value:

                # DELETE THIS ONLY FOR TESTING
                #temp_amplitude=peak_value

                # Get the center of mass peak value
                sum_of_positions_times_values=0
                sum_of_values=0
                number_of_positions_to_test=7 # odd value
                poswidth=int(number_of_positions_to_test/2)

                for spotty in range(number_of_positions_to_test):
                    sum_of_positions_times_values=sum_of_positions_times_values+(actualprofile[peak_value_index-poswidth+spotty][1]*actualprofile[peak_value_index-poswidth+spotty][0])
                    sum_of_values=sum_of_values+actualprofile[peak_value_index-poswidth+spotty][1]
                peak_position=(sum_of_positions_times_values / sum_of_values)

                temppos=abs(actualprofile[:,0] - peak_position).argmin()
                tempvalue=actualprofile[temppos,1]
                temppeakvalue=copy.deepcopy(tempvalue)

                # Get lefthand quarter percentiles
                counter=1
                while tempvalue > 0.25*temppeakvalue:

                    tempvalue=actualprofile[temppos-counter,1]
                    if tempvalue > 0.75:
                        threequartertemp=temppos-counter
                    #print (tempvalue)
                    counter=counter+1

                lefthand_quarter_spot=actualprofile[temppos-counter][0]
                lefthand_threequarter_spot=actualprofile[threequartertemp][0]

                # Get righthand quarter percentile
                counter=1
                while tempvalue > 0.25*temppeakvalue:
                    tempvalue=actualprofile[temppos+counter,1]
                    #print (tempvalue)
                    if tempvalue > 0.75:
                        threequartertemp=temppos+counter
                    counter=counter+1

                righthand_quarter_spot=actualprofile[temppos+counter][0]
                righthand_threequarter_spot=actualprofile[threequartertemp][0]

                largest_reasonable_position_deviation_in_pixels=1.25*max(abs(peak_position - righthand_quarter_spot),abs(peak_position - lefthand_quarter_spot))
                largest_reasonable_position_deviation_in_arcseconds=largest_reasonable_position_deviation_in_pixels *pixscale

                smallest_reasonable_position_deviation_in_pixels=0.7*min(abs(peak_position - righthand_threequarter_spot),abs(peak_position - lefthand_threequarter_spot))
                smallest_reasonable_position_deviation_in_arcseconds=smallest_reasonable_position_deviation_in_pixels *pixscale

                # If peak reasonably in the center
                # And the largest reasonable position deviation isn't absurdly small
                if abs(peak_position) < max(3, 3/pixscale) and largest_reasonable_position_deviation_in_arcseconds > 1.0:



                    # Construct testing array
                    # Initially on pixelscale then convert to pixels
                    testvalue=0.1
                    testvalues=[]
                    while testvalue < 12:
                        if testvalue > smallest_reasonable_position_deviation_in_arcseconds and testvalue < largest_reasonable_position_deviation_in_arcseconds:
                            if testvalue > 1 and testvalue <= 7:
                                testvalues.append(testvalue)
                                testvalues.append(testvalue+0.05)
                            elif testvalue > 7:
                                if (int(testvalue * 10) % 3) == 0 :
                                    testvalues.append(testvalue)
                            else:
                                testvalues.append(testvalue)
                        testvalue=testvalue+0.1
                    # convert pixelscales into pixels
                    pixel_testvalues=np.array(testvalues) / pixscale
                    # convert fwhm into appropriate stdev
                    pixel_testvalues=(pixel_testvalues/2.355) /2


                    smallest_value=999999999999999.9
                    for pixeltestvalue in pixel_testvalues:

                        test_fpopt= [peak_value, peak_position, pixeltestvalue]


                        # differences between gaussian and data
                        difference=(np.sum(abs(actualprofile[:,1] - gaussian(actualprofile[:,0], *test_fpopt))))

                        if difference < smallest_value:
                            smallest_value=copy.deepcopy(difference)
                            smallest_fpopt=copy.deepcopy(test_fpopt)

                        if difference < 1.25 * smallest_value:
                            # print (time.time()-googtime)
                            # plt.scatter(actualprofile[:,0],actualprofile[:,1])
                            # plt.plot(actualprofile[:,0], gaussian(actualprofile[:,0], *test_fpopt),color = 'r')
                            # # plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
                            # plt.show()
                            pass
                        else:
                            break



                    # Amplitude has to be a substantial fraction of the peak value
                    # and the center of the gaussian needs to be near the center
                    # and the FWHM has to be above 0.8 arcseconds.
                    #if popt[0] > (0.5 * cvalue) and abs(popt[1]) < max(3, 3/pixscale):# and (2.355 * popt[2]) > (0.8 / pixscale) :

                    # if it isn't a unreasonably small fwhm then measure it.
                    try:
                        if (2.355 * smallest_fpopt[2]) > (0.8 / pixscale) :

                            # plt.scatter(actualprofile[:,0],actualprofile[:,1])
                            # plt.plot(actualprofile[:,0], gaussian(actualprofile[:,0], *smallest_fpopt),color = 'r')

                            # #plt.plot(actualprofile[:,0], gaussian(actualprofile[:,0], *popt),color = 'g')
                            # #plt.axvline(x = 0, color = 'g', label = 'axvline - full height')
                            # plt.show()

                            return smallest_fpopt[2]
                        else:
                            return np.nan
                    except:
                        return np.nan

        # If rejected by some if statement, return nan
        return np.nan
    except:
        plog(traceback.format_exc())
        #breakpoint()
        return np.nan



class Camera:
    """A camera instrument.

    The filter, focuser, rotator must be set up prior to camera.
    Since this is a class definition we need to pre-enter with a list of classes
    to be created by a camera factory.
    """

    def __init__(self, driver: str, name: str, config: dict):
        """
        Added monkey patches to make ASCOM/Maxim/TheSkyX/QHY differences
        go away from the bulk of the in-line code.
        """

        self.last_user_name = "none"
        self.last_user_id = "none"
        self.user_name = "none"
        self.user_id = "none"

        self.name = name
        self.driver = driver
        g_dev[name + "_cam_retry_driver"] = driver
        g_dev[name + "_cam_retry_name"] = name
        g_dev[name + "_cam_retry_config"] = config
        g_dev[name + "_cam_retry_doit"] = False
        g_dev[name] = self
        if name == "camera_1_1":  # NBDefaults sets up Selected 'cam'
            g_dev["cam"] = self
        self.config = config
        self.alias = config["camera"][self.name]["name"]

        win32com.client.pythoncom.CoInitialize()
        plog(driver, name)

        if not driver == "QHYCCD_Direct_Control":
            self.camera = win32com.client.Dispatch(driver)
        else:
            self.camera = None
        self.async_exposure_lock=False # This is needed for TheSkyx (and maybe future programs) where the
                                       # exposure has to be called from a separate thread and then waited
                                       # for in the main thread

        # Sets up paths and structures
        self.obsid_path = g_dev['obs'].obsid_path
        if not os.path.exists(self.obsid_path):
            os.makedirs(self.obsid_path)
        self.local_calibration_path = g_dev['obs'].local_calibration_path
        if not os.path.exists(self.local_calibration_path):
            os.makedirs(self.local_calibration_path)

        self.archive_path = self.config["archive_path"] + self.config['obs_id'] + '/'+ "archive/"
        if not os.path.exists(self.config["archive_path"] +'/' + self.config['obs_id']):
            os.makedirs(self.config["archive_path"] +'/' + self.config['obs_id'])
        if not os.path.exists(self.config["archive_path"] +'/' + self.config['obs_id']+ '/'+ "archive/"):
            os.makedirs(self.config["archive_path"] +'/' + self.config['obs_id']+ '/'+ "archive/")
        self.camera_path = self.archive_path + self.alias + "/"
        if not os.path.exists(self.camera_path):
            os.makedirs(self.camera_path)
        self.alt_path = self.config[
            "alt_path"
        ]  +'/' + self.config['obs_id']+ '/' # NB NB this should come from config file, it is site dependent.
        if not os.path.exists(self.config[
            "alt_path"
        ]):
            os.makedirs(self.config[
            "alt_path"
        ])

        if not os.path.exists(self.alt_path):
            os.makedirs(self.alt_path)
        self.autosave_path = self.camera_path + "autosave/"
        self.lng_path = self.camera_path + "lng/"
        self.seq_path = self.camera_path + "seq/"
        # if not os.path.exists(self.autosave_path):  #obsolete WER 20240106
        #     os.makedirs(self.autosave_path)
        # if not os.path.exists(self.lng_path):
        #     os.makedirs(self.lng_path)
        # if not os.path.exists(self.seq_path):
        #     os.makedirs(self.seq_path)

        # Just need to initialise this filter thing
        self.current_offset  = 0
        self.current_filter= None


        self.updates_paused=False

        """
        This section loads in the calibration files for flash calibrations
        """
        plog("loading flash dark, bias and flat master frames if available")
        self.biasFiles = {}
        self.darkFiles = {}
        self.flatFiles = {}
        #self.hotFiles = {}
        self.bpmFiles = {}


        g_dev['obs'].obs_id
        g_dev['cam'].alias
        tempfrontcalib=g_dev['obs'].obs_id + '_' + g_dev['cam'].alias +'_'

        try:
            tempbiasframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib + "BIAS_master_bin1.fits")
            tempbiasframe = np.array(tempbiasframe[0].data, dtype=np.float32)
            self.biasFiles.update({'1': tempbiasframe})
            del tempbiasframe
        except:
            plog("Bias frame for Binning 1 not available")

        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "DARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'1': tempdarkframe})
            del tempdarkframe
        except:
            plog("Long Dark frame for Binning 1 not available")


        # try:
        #     tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
        #                               + "/" + tempfrontcalib +  "DARK_master_bin1.fits")

        #     tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
        #     self.darkFiles.update({'1': tempdarkframe})
        #     del tempdarkframe
        # except:
        #     plog("Long Dark frame for Binning 1 not available")


        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "halfsecondDARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'halfsec_exposure_dark': tempdarkframe})
            del tempdarkframe
        except:
            plog("0.5s Dark frame for Binning 1 not available")

        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "2secondDARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'twosec_exposure_dark': tempdarkframe})
            del tempdarkframe
        except:
            plog("2.0s Dark frame for Binning 1 not available")

        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "10secondDARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'tensec_exposure_dark': tempdarkframe})
            del tempdarkframe
        except:
            plog("10.0s Dark frame for Binning 1 not available")

        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "tensecBIASDARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'tensec_exposure_biasdark': tempdarkframe})
            del tempdarkframe
        except:
            plog("10.0s Bias Dark frame for Binning 1 not available")

        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "broadbandssDARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'broadband_ss_dark': tempdarkframe})
            del tempdarkframe
        except:
            plog("Broadband Smartstack Length Dark frame for Binning 1 not available")

        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "broadbandssBIASDARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'broadband_ss_biasdark': tempdarkframe})
            del tempdarkframe
        except:
            plog("Broadband Smartstack Length Bias Dark frame for Binning 1 not available")

        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "narrowbandssDARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'narrowband_ss_dark': tempdarkframe})
            del tempdarkframe
        except:
            plog("Narrowband Smartstack Length Dark frame for Binning 1 not available")

        try:
            tempdarkframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
                                      + "/" + tempfrontcalib +  "narrowbandssBIASDARK_master_bin1.fits")

            tempdarkframe = np.array(tempdarkframe[0].data, dtype=np.float32)
            self.darkFiles.update({'narrowband_ss_biasdark': tempdarkframe})
            del tempdarkframe
        except:
            plog("Narrowband Smartstack Length Bias Dark frame for Binning 1 not available")

        try:
            # tempbpmframe = fits.open(self.local_calibration_path + "archive/" + self.alias + "/calibmasters" \
            #                           + "/" + tempfrontcalib +  "badpixelmask_bin1.npy")

            # tempbpmframe = np.array(tempbpmframe[0].data, dtype=np.float32)
            tempbpmframe = np.load(self.local_calibration_path + "archive/" + self.alias + "/calibmasters/" + tempfrontcalib +  "badpixelmask_bin1.npy")
            #breakpoint()
            # For live observing, ignore bad pixels on crusty edges
            # At the edges they can be full columns or large patches of
            # continuous areas which take too long to interpolate quickly.
            # The full PIPE run does not ignore these.
            tempbpmframe[:,:75] = False
            tempbpmframe[:75,:] = False
            tempbpmframe[-75:,:] = False
            tempbpmframe[:,-75:] = False

            self.bpmFiles.update({'1': tempbpmframe})
            del tempbpmframe
        except:
            plog("Bad Pixel Mask for Binning 1 not available")


        #breakpoint()

        try:
            fileList = glob.glob(self.local_calibration_path + "archive/" + self.alias + "/calibmasters/masterFlat*_bin1.npy")
            for file in fileList:
                # if self.config['camera'][self.name]['settings']['hold_flats_in_memory']:
                #     tempflatframe=np.load(file)
                #     self.flatFiles.update({file.split('_')[-2]: np.array(tempflatframe)})
                #     del tempflatframe
                # else:
                self.flatFiles.update({file.split("_")[1].replace ('.npy','') + '_bin1': file})
            # To supress occasional flatfield div errors
            np.seterr(divide="ignore")
        except:
            plog("Flat frames not loaded or available")


        self.shutter_open = False # Initialise
        self.substacker = False # Initialise

        """
        This section connects the appropriate methods for various
        camera actions for various drivers. Each separate software
        has it's own unique and annoying way of doing things'
        """

        plog("Connecting to:  ", driver)

        if driver[:5].lower() == "ascom":
            plog("ASCOM camera is initializing.")
            self._connected = self._ascom_connected
            self._connect = self._ascom_connect
            self._set_setpoint = self._ascom_set_setpoint
            self._setpoint = self._ascom_setpoint
            self._temperature = self._ascom_temperature
            self._cooler_on = self._ascom_cooler_on
            self._set_cooler_on = self._ascom_set_cooler_on
            self._expose = self._ascom_expose
            self._stop_expose = self._ascom_stop_expose
            self._imageavailable = self._ascom_imageavailable
            self._getImageArray = self._ascom_getImageArray
            self.description = "ASCOM"
            self.maxim = False
            self.ascom = True
            self.theskyx = False
            self.qhydirect = False

            self.camera.Connected = True
            plog("ASCOM is connected:  ", self._connect(True))

            plog("Control is ASCOM camera driver.")
            self.camera.Connected = True
            time.sleep(0.2)
            if self.camera.Connected:
                plog("ASCOM camera is connected:  ", self._connect(True))
            else:
                plog("ERROR:  ASCOM camera is not connected:  ", self._connect(True))
            #breakpoint()

            self.imagesize_x = self.camera.CameraXSize
            self.imagesize_y = self.camera.CameraYSize

        elif driver == "CCDSoft2XAdaptor.ccdsoft5Camera":
            plog("Connecting to TheSkyX")
            self._connected = self._theskyx_connected
            self._connect = self._theskyx_connect
            self._set_setpoint = self._theskyx_set_setpoint
            self._setpoint = self._theskyx_setpoint
            self._temperature = self._theskyx_temperature
            self._cooler_on = self._theskyx_cooler_on
            self._set_cooler_on = self._theskyx_set_cooler_on
            self._expose = self._theskyx_expose
            self._stop_expose = self._theskyx_stop_expose
            self._imageavailable = self._theskyx_imageavailable
            self._getImageArray = self._theskyx_getImageArray

            self.camera.Connect()
            self.camera.AutoSaveOn = 1
            self.camera.Subframe = 0
            self.description = "TheSkyX"
            self.maxim = False
            self.ascom = False
            self.theskyx = True
            self.qhydirect = False
            plog("TheSkyX is connected:  ")
            self.app = win32com.client.Dispatch("CCDSoft2XAdaptor.ccdsoft5Camera")


            # Initialise Camera Size here
            # Take a quick cheeky frame to get imagesize
            tempcamera = win32com.client.Dispatch(self.driver)
            tempcamera.Connect()
            self._stop_expose()
            tempcamera.Frame=2
            tempcamera.ExposureTime=0
            tempcamera.ImageReduction=0
            tempcamera.TakeImage()
            imageTempOpen=fits.open(tempcamera.LastImageFileName, uint=False)[0].data.astype("float32")


            del tempcamera

            try:
                os.remove(self.camera.LastImageFileName)
            except Exception as e:
                plog ("Could not remove theskyx image file: ",e)

            self.imagesize_x=int(imageTempOpen.shape[0])
            self.imagesize_y=int(imageTempOpen.shape[1])
            del imageTempOpen



        elif driver == "QHYCCD_Direct_Control":
            global qhycam
            plog("Connecting directly to QHY")
            qhycam = Qcam(os.path.join("support_info/qhysdk/x64/qhyccd.dll"))

            qhycam.so.RegisterPnpEventIn(pnp_in)
            qhycam.so.RegisterPnpEventOut(pnp_out)
            qhycam.so.InitQHYCCDResource()
            qhycam.camera_params[qhycam_id]['handle'] = qhycam.so.OpenQHYCCD(qhycam_id)
            if qhycam.camera_params[qhycam_id]['handle'] is None:
                print('open camera error %s' % cam_id)

            read_mode=self.config["camera"][self.name]["settings"]['direct_qhy_readout_mode']
            numModes=c_int32()
            success = qhycam.so.SetQHYCCDReadMode(qhycam.camera_params[qhycam_id]['handle'], read_mode)

            qhycam.camera_params[qhycam_id]['stream_mode'] = c_uint8(qhycam.stream_single_mode)
            success = qhycam.so.SetQHYCCDStreamMode(qhycam.camera_params[qhycam_id]['handle'], qhycam.camera_params[qhycam_id]['stream_mode'])

            success = qhycam.so.InitQHYCCD(qhycam.camera_params[qhycam_id]['handle'])

            mode_name = create_string_buffer(qhycam.STR_BUFFER_SIZE)
            qhycam.so.GetReadModeName(qhycam_id, read_mode, mode_name) # 0 is Photographic DSO 16 bit
            read_mode_name_str = mode_name.value.decode('utf-8').replace(' ', '_')
            plog ("Read Mode: "+ read_mode_name_str)

            success = qhycam.so.SetQHYCCDBitsMode(qhycam.camera_params[qhycam_id]['handle'], c_uint32(qhycam.bit_depth_16))

            success = qhycam.so.GetQHYCCDChipInfo(qhycam.camera_params[qhycam_id]['handle'],
                                               byref(qhycam.camera_params[qhycam_id]['chip_width']),
                                               byref(qhycam.camera_params[qhycam_id]['chip_height']),
                                               byref(qhycam.camera_params[qhycam_id]['image_width']),
                                               byref(qhycam.camera_params[qhycam_id]['image_height']),
                                               byref(qhycam.camera_params[qhycam_id]['pixel_width']),
                                               byref(qhycam.camera_params[qhycam_id]['pixel_height']),
                                               byref(qhycam.camera_params[qhycam_id]['bits_per_pixel']))

            qhycam.camera_params[qhycam_id]['mem_len'] = qhycam.so.GetQHYCCDMemLength(qhycam.camera_params[qhycam_id]['handle'])
            i_w = qhycam.camera_params[qhycam_id]['image_width'].value
            i_h = qhycam.camera_params[qhycam_id]['image_height'].value

            qhycam.camera_params[qhycam_id]['prev_img_data'] = (c_uint16 * int(qhycam.camera_params[qhycam_id]['mem_len'] / 2))()

            success = qhycam.QHYCCD_ERROR

            qhycam.so.SetQHYCCDResolution(qhycam.camera_params[qhycam_id]['handle'], c_uint32(0), c_uint32(0), c_uint32(i_w),
                                           c_uint32(i_h))
            image_width_byref = c_uint32()
            image_height_byref = c_uint32()
            bits_per_pixel_byref = c_uint32()

            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(20000))
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_GAIN, c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_gain'])))
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_OFFSET, c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_offset'])))
            #success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_USBTRAFFIC,c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_usb_speed'])))
            #success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_USBTRAFFIC,c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_usb_traffic'])))

            if self.config["camera"][self.name]["settings"]['set_qhy_usb_speed']:
                success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_SPEED,c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_usb_traffic'])))
            plog('Set QHY conversion Gain: ', self.config["camera"][self.name]["settings"]['direct_qhy_gain'])
            plog('Set QHY Offset: ', self.config["camera"][self.name]["settings"]['direct_qhy_offset'])
            plog('Set QHY USB speed to: ', self.config["camera"][self.name]["settings"]['direct_qhy_usb_traffic'])  # NB NB ideally we should read this back to verify.

            self._connected = self._qhyccd_connected
            self._connect = self._qhyccd_connect
            self._set_setpoint = self._qhyccd_set_setpoint
            self._setpoint = self._qhyccd_setpoint
            self._temperature = self._qhyccd_temperature
            self._cooler_on = self._qhyccd_cooler_on
            self._set_cooler_on = self._qhyccd_set_cooler_on
            self._expose = self._qhyccd_expose
            self._stop_expose = self._qhyccd_stop_expose
            self._imageavailable = self._qhyccd_imageavailable
            self._getImageArray = self._qhyccd_getImageArray




            self.description = "QHYDirectControl"
            self.maxim = False
            self.ascom = False
            self.theskyx = False
            self.qhydirect = True


            # Initialise Camera Size here
            self.imagesize_x=int(i_h)
            self.imagesize_y=int(i_w)
            #breakpoint()

        else:
            # NB NB NB Considerputting this up higher.
            plog("Maxim camera is initializing.")
            self._connected = self._maxim_connected
            self._connect = self._maxim_connect
            self._set_setpoint = self._maxim_set_setpoint
            self._setpoint = self._maxim_setpoint
            self._temperature = self._maxim_temperature
            self._cooler_on = self._maxim_cooler_on
            self._set_cooler_on = self._maxim_set_cooler_on
            self._expose = self._maxim_expose
            self._stop_expose = self._maxim_stop_expose
            self._imageavailable = self._maxim_imageavailable
            self._getImageArray = self._maxim_getImageArray

            self.description = "MAXIM"
            self.maxim = True
            self.ascom = False
            self.theskyx = False
            self.qhydirect = False
            plog("Maxim is connected:  ", self._connect(True))
            self.app = win32com.client.Dispatch("Maxim.Application")
            plog(self.camera)
            self.camera.SetFullFrame()
            self.camera.SetFullFrame

            self.imagesize_x = self.camera.CameraXSize
            self.imagesize_y = self.camera.CameraYSize

            plog("Control is via Maxim camera interface, not ASCOM.")
            plog("Please note telescope is NOT connected to Maxim.")

        # Before anything, abort any exposures because sometimes a long exposure
        # e.g. 500s could keep on going with theskyx (and maybe Maxim)
        # and still be going on at a restart and crash the connection
        try:
            self._stop_expose()
        except:
            pass

        # Camera cooling setup
        self.setpoint = float(self.config["camera"][self.name]["settings"]["temp_setpoint"]) # This is the config setpoint
        try:
            self.temp_tolerance = float(self.config["camera"][self.name]["settings"]["temp_setpoint_tolarance"])
        except:
            self.temp_tolerance = 1.5
            plog ("temp tolerance isn't set in obs config, using 1.5 degrees")
        self.current_setpoint =  float(self.config["camera"][self.name]["settings"]["temp_setpoint"]) # This setpoint can change if there is camera warming during the day etc.
        self._set_setpoint(self.setpoint)
        self.day_warm = float(self.config["camera"][self.name]["settings"]['day_warm'])
        self.day_warm_degrees = float(self.config["camera"][self.name]["settings"]['day_warm_degrees'])
        self.protect_camera_from_overheating=float(self.config["camera"][self.name]["settings"]['protect_camera_from_overheating'])
# =============================================================================
#         # NB NB *** No logic here to manage chillers and water cooling. ***
# =============================================================================
        plog("Cooler setpoint is now:  ", self.setpoint)
        if self.config["camera"][self.name]["settings"][
            "cooler_on"
        ]:  # NB NB why this logic, do we mean if not cooler found on, then turn it on and take the delay?
            self._set_cooler_on()
        if self.theskyx:
            temp, humid, pressure =self.camera.Temperature, 999.9, 999.9
        else:
            temp, humid, pressure =self._temperature()
        plog("Cooling beginning @:  ", temp)
        if 1 <= humid <= 100 or 1 <= pressure <=1100:
            plog("Humidity and pressure:  ", humid, pressure)
        else:
            plog("Camera temp and pressure is not reported.")

        if self.maxim == True:
            plog("TEC  % load:  ", self._maxim_cooler_power())
        else:
            plog("TEC% load is  not reported.")

        self.running_an_exposure_set = False
        self.currently_in_smartstack_loop=False

        self.start_time_of_observation = time.time()
        self.current_exposure_time = 20


        self.end_of_last_exposure_time=time.time()


        self.camera_update_reboot=False

        #expresult={}



        # Figure out pixelscale from own observations
        # Or use the config value if there hasn't been enough
        # observations yet.
        try:
            self.pixelscale_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].alias + str(g_dev['obs'].name))
            try:
                pixelscale_list=self.pixelscale_shelf['pixelscale_list']
            except:
                pixelscale_list=[]

            self.pixelscale_shelf.close()

            #if len(pixelscale_list) > 5:
            self.pixscale = bn.nanmedian(pixelscale_list)
            # else:
            #     self.pixscale = None
                # SUPER TEMPORARY HACK SO  MTF CAN GO DEBUG SOMETHING
                #self.pixscale=0.288
                #self.pixscale = 0.198

            plog('1x1 pixel scale: ' + str(self.pixscale))
        except:
            plog ("ALERT: PIXELSCALE SHELF CORRUPTED. WIPING AND STARTING AGAIN")
            self.pixscale = None
            plog(traceback.format_exc())
            try:
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.dat'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.dat')
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.dir'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.dir')
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.bak'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.bak')

                # self.pixelscale_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].alias + str(g_dev['obs'].name))
                # pixelscale_list=[]
                # self.pixelscale_shelf['pixelscale_list'] = pixelscale_list
                # self.pixelscale_shelf.close()

            except:
                plog(traceback.format_exc())
                breakpoint()

        #breakpoint()

        """
        TheSkyX runs on a file mode approach to images rather
        than a direct readout from the camera, so this path
        is set here.
        """
        if (
            self.config["camera"]["camera_1_1"]["driver"]
            == "CCDSoft2XAdaptor.ccdsoft5Camera"
        ):

            self.camera.AutoSavePath = (
                self.archive_path
                + datetime.datetime.strftime(datetime.datetime.now(), "%Y%m%d")
            )
            try:
                os.mkdir(
                    self.archive_path
                    + datetime.datetime.strftime(datetime.datetime.now(), "%Y%m%d")
                )
            except:
                plog("Couldn't make autosave directory")

        """
        Actually not sure if this is useful anymore if there are no differences
        between ccds and cmoses? This may just be used for the fits header
        at the end of the day.  Yes I just want to inform the user downstream and or
        trigger Telegraph noise correction -- all TBD.    We will have CCD
        Cameras in the mix.WER
        """
        if self.config["camera"][self.name]["settings"]["is_cmos"] == True:
            self.is_cmos = True
        else:
            self.is_cmos = False



        if self.config["camera"][self.name]["settings"]["dither_enabled"] == True:
            self.dither_enabled = True
        else:
            self.dither_enabled = False

        if self.config["camera"][self.name]["settings"]['is_osc'] == True:
            self.is_osc = True
        else:
            self.is_osc = False


        self.camera_model = self.config["camera"][self.name]["desc"]
        # NB We are reading from the actual camera or setting as the case may be. For initial setup,
        # we pull from config for some of the various settings.
        if self.camera is not None:
            try:
                self.camera.BinX = 1
                self.camera.BinY = 1
            except:
                plog("Problem setting up 1x1 binning at startup.")

        self.has_darkslide = False
        self.darkslide_state = "N.A."   #Not Available.
        #breakpoint()
        if self.config["camera"][self.name]["settings"]["has_darkslide"]:
            self.has_darkslide = True
            self.darkslide_state = 'Unknown'
            self.darkslide_type=self.config["camera"][self.name]["settings"]['darkslide_type']

            com_port = self.config["camera"][self.name]["settings"]["darkslide_com"]
            if self.darkslide_type=='bistable':
                self.darkslide_instance = Darkslide(com_port)
            #elif self.darkslide_type='ASCOM_FLI_SHUTTER':  #this must be the Fli.ASCOM version
                #self.darkslide_instance = self.camera
                #breakpoint()
                #Michael I stop here. There is one reference to darkslide in Sequencer line 2668
            # As it takes 12seconds to open, make sure it is either Open or Shut at startup
            if self.darkslide_state != 'Open':

                if self.darkslide_type is not None:
                    self.darkslide_instance.openDarkslide()
                    ####I think we just need to add open and closeDarkslide methods to the camera class and
                    ####make the calls outlined in the PDF  note lower case open and close strings to the ASCOM driver
                    self.darkslide_open = True
                    self.darkslide_state = 'Open'
                elif self.darkslide_type=='ASCOM_FLI_KEPLER':
                    self.camera.Action('SetShutter', 'open')
                    self.darkslide_open = True
                    self.darkslide_state = 'Open'


            ###See lines around 766 for local methods


        self.camera_known_gain=70000.0
        self.camera_known_gain_stdev=70000.0
        self.camera_known_readnoise=70000.0
        self.camera_known_readnoise_stdev=70000.0

        try:
            next_seq = next_sequence(self.config["camera"][self.name]["name"])
        except:
            next_seq = reset_sequence(self.config["camera"][self.name]["name"])
        self.next_seq= next_seq

        #breakpoint()
        # if True:
        try:

            gain_collector=[]
            stdev_collector=[]

            self.filter_camera_gain_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + g_dev['cam'].alias + str(g_dev['obs'].name))

            for entry in self.filter_camera_gain_shelf:
                if entry != 'readnoise':
                    singlentry=self.filter_camera_gain_shelf[entry]
                    #if singlentry[2] > int(0.8 * self.config['camera'][self.name]['settings']['number_of_flat_to_store']):
                    gain_collector.append(singlentry[0])
                    stdev_collector.append(singlentry[1])
                        # if singlentry[0] < self.camera_known_gain:
                        #     self.camera_known_gain=singlentry[0]
                        #     self.camera_known_gain_stdev=singlentry[1]


            if len(gain_collector) > 1:

                while True:
                    print (gain_collector)
                    gainmed=bn.nanmedian(gain_collector)
                    print (gainmed)
                    gainstd=np.nanstd(gain_collector)
                    print (gainstd)
                    new_gain_pile=[]
                    new_stdev_pile=[]
                    counter=0
                    for entry in gain_collector:
                        if entry < gainmed + 3* gainstd:
                            new_gain_pile.append(entry)
                            new_stdev_pile.append(stdev_collector[counter])
                        counter=counter+1
                    if len(new_gain_pile) == len(gain_collector):
                        break
                    if len(new_gain_pile) == 1:
                        self.camera_known_gain=new_gain_pile[0]
                        self.camera_known_gain_stdev=new_gain_pile[0]
                        break

                    gain_collector=copy.deepcopy(new_gain_pile)
                    stdev_collector=copy.deepcopy(new_stdev_pile)

                self.camera_known_gain=gainmed
                self.camera_known_gain_stdev=np.nanstd(gain_collector)
            else:
                self.camera_known_gain=gain_collector[0]
                self.camera_known_gain_stdev=stdev_collector[0]
            #breakpoint()

            singlentry=self.filter_camera_gain_shelf['readnoise']
            self.camera_known_readnoise= (singlentry[0] * self.camera_known_gain) / 1.414
            self.camera_known_readnoise_stdev = (singlentry[1] * self.camera_known_gain) / 1.414
        except:
            plog('failed to estimate gain and readnoise from flats and such')
        #         self.camera_known_gain=self.config["camera"][self.name]["settings"]["camera_gain"]
        #         self.camera_known_gain_stdev=self.config["camera"][self.name]["settings"]['camera_gain_stdev']
        #         self.camera_known_readnoise=self.config["camera"][self.name]["settings"]['read_noise']
        #         self.camera_known_readnoise_stdev=self.config["camera"][self.name]["settings"]['read_noise_stdev']

        # else:
        #     self.camera_known_gain=self.config["camera"][self.name]["settings"]["camera_gain"]
        #     self.camera_known_gain_stdev=self.config["camera"][self.name]["settings"]['camera_gain_stdev']
        #     self.camera_known_readnoise=self.config["camera"][self.name]["settings"]['read_noise']
        #     self.camera_known_readnoise_stdev=self.config["camera"][self.name]["settings"]['read_noise_stdev']

        plog ("Used Camera Gain: " + str(self.camera_known_gain))
        plog ("Used Readnoise  : "+ str(self.camera_known_readnoise))

        try:
            seq = test_sequence(self.alias)
        except:
            plog ("Sequence number failed to load. Starting from zero.")
            plog(traceback.format_exc())
            reset_sequence(self.alias)
        try:
            self._stop_expose()
        except:
            pass


        self.post_processing_queue = queue.Queue(maxsize=0)
        self.post_processing_queue_thread = threading.Thread(target=self.post_processing_process, args=())
        self.post_processing_queue_thread.daemon = True
        self.post_processing_queue_thread.start()



        # Load in previous estimates of readout_time
        try:
            self.readout_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + g_dev['cam'].alias + str(g_dev['obs'].name))
            try:
                readout_list=self.readout_shelf['readout_list']
            except:
                readout_list=[]

            self.readout_shelf.close()

            if len(readout_list) > 0:
                self.readout_time = bn.nanmedian(readout_list)
            else:
                self.readout_time = 0 # if it is zero, thats fine, it will estimate the readout time on the first readout.

            plog ("Currently estimated readout time: " + str(self.readout_time))
        #self.readout_time=0

        except:
            plog ("ALERT: READOUT SHELF CORRUPTED. WIPING AND STARTING AGAIN")
            self.pixscale = None
            plog(traceback.format_exc())
            try:
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.dat'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.dat')
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.dir'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' +'readout' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.dir')
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.bak'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + g_dev['cam'].alias + str(g_dev['obs'].name) +'.bak')

                # self.pixelscale_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + g_dev['cam'].alias + str(g_dev['obs'].name))
                # pixelscale_list=[]
                # self.pixelscale_shelf['pixelscale_list'] = pixelscale_list
                # self.pixelscale_shelf.close()

            except:
                plog(traceback.format_exc())
                breakpoint()





        if self.theskyx:


            self.theskyx_set_cooler_on=True
            self.theskyx_cooleron=True
            self.theskyx_set_setpoint_trigger=True
            self.theskyx_set_setpoint_value= self.setpoint
            self.theskyx_temperature=self.camera.Temperature, 999.9, 999.9
            self.camera_update_period=5
            self.camera_update_timer=time.time() - 2* self.camera_update_period
            self.camera_updates=0
            #self.focuser_update_thread_queue = queue.Queue(maxsize=0)
            self.camera_update_thread=threading.Thread(target=self.camera_update_thread)
            self.camera_update_thread.daemon = True
            self.camera_update_thread.start()


    def openDarkslide(self):
        if self.darkslide_state != 'Open':
            if self.darkslide_type is not None:
                opened=self.darkslide_instance.openDarkslide()
            elif self.darkslide_type=='ASCOM_FLI_SHUTTER':
                self.camera.Action('SetShutter', 'open')
            if opened:
                self.darkslide_open = True
                self.darkslide_state = 'Open'
                return False
            else:
                return True






    def closeDarkslide(self):
        if self.darkslide_state != 'Closed':
            if self.darkslide_type is not None:
                closed=self.darkslide_instance.closeDarkslide()
            elif self.darkslide_type=='ASCOM_FLI_Kepler':    #NB NB this logic is faulty wer
                self.camera.Action('SetShutter', 'close')
            if closed:
                self.darkslide_open = False
                self.darkslide_state = 'Closed'
                return False
            else:
                return True


    # # Note this is a thread!
    # def write_raw_file_out(self,packet):

    #     (raw, raw_name, hdudata, hduheader, frame_type, current_icrs_ra, current_icrs_dec,altpath,altfolder) = packet

    #     print ("RAW RECEIVED: " + str(raw_name) )


    #     # Make sure normal paths exist
    #     os.makedirs(
    #         g_dev['cam'].camera_path + g_dev["day"], exist_ok=True
    #     )
    #     os.makedirs(
    #         g_dev['cam'].camera_path + g_dev["day"] + "/raw/", exist_ok=True
    #     )
    #     os.makedirs(
    #         g_dev['cam'].camera_path + g_dev["day"] + "/reduced/", exist_ok=True
    #     )
    #     os.makedirs(
    #         g_dev['cam'].camera_path + g_dev["day"] + "/calib/", exist_ok=True)


    #     # Make  sure the alt paths exist
    #     if raw == 'raw_alt_path':
    #         os.makedirs(
    #             altpath + g_dev["day"], exist_ok=True
    #         )
    #         os.makedirs(
    #             altpath + g_dev["day"] + "/raw/", exist_ok=True
    #         )
    #         os.makedirs(
    #             altpath + g_dev["day"] + "/reduced/", exist_ok=True
    #         )
    #         os.makedirs(
    #             altpath + g_dev["day"] + "/calib/", exist_ok=True)

    #         # altfolder = self.config['temporary_local_alt_archive_to_hold_files_while_copying']
    #         # if not os.path.exists(self.config['temporary_local_alt_archive_to_hold_files_while_copying']):
    #         #     os.makedirs(self.config['temporary_local_alt_archive_to_hold_files_while_copying'] )



    #     hdu = fits.PrimaryHDU()
    #     hdu.data = hdudata
    #     hdu.header = hduheader
    #     hdu.header["DATE"] = (
    #         datetime.date.strftime(
    #             datetime.datetime.utcfromtimestamp(time.time()), "%Y-%m-%d"
    #         ),
    #         "Date FITS file was written",
    #     )
    #     if raw == 'raw_alt_path':# or slow_process[0] == 'reduced_alt_path':
    #         #breakpoint()
    #         hdu.writeto( altfolder +'/' + raw_name.split('/')[-1].replace('EX00','EX00-'+hduheader['OBSTYPE']), overwrite=True, output_verify='silentfix'
    #         )  # Save full raw file locally
    #         self.altarchive_queue.put((copy.deepcopy(altfolder +'/' + raw_name.split('/')[-1].replace('EX00','EX00-'+hduheader['OBSTYPE'])),copy.deepcopy(raw_name),time.time()), block=False)
    #     else:
    #         hdu.writeto(
    #             raw_name.replace('EX00','EX00-'+hduheader['OBSTYPE']), overwrite=True, output_verify='silentfix'
    #         )  # Save full raw file locally
    #     try:
    #         hdu.close()
    #     except:
    #         pass
    #     del hdu
    #     #     saver = 1

    #     # except Exception as e:
    #     #     plog("Failed to write raw file: ", e)
    #     #     plog(traceback.format_exc())
    #     #         # if "requested" in e and "written" in e:
    #     #         #     plog(check_download_cache())
    #     #         # plog(traceback.format_exc())
    #     #         # time.sleep(10)
    #     #         # saverretries = saverretries + 1

    #     print ("RAW PROCESSED: " + str(raw_name) )

    def in_line_quick_focus(self, hdufocusdata, im_path, text_name):

        googtime=time.time()
        # Check there are no nans in the image upon receipt
        # This is necessary as nans aren't interpolated in the main thread.
        # Fast next-door-neighbour in-fill algorithm
        #num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))
        #x_size=hdufocusdata.shape[0]
        #y_size=hdufocusdata.shape[1]


        bkg = sep.Background(hdufocusdata, bw=32, bh=32, fw=3, fh=3)
        bkg.subfrom(hdufocusdata)

        # this is actually faster than np.nanmean
        imageMedian=bn.nanmedian(hdufocusdata)
        # Mop up any remaining nans
        hdufocusdata[np.isnan(hdufocusdata)] =imageMedian



        # Cut down focus image to central degree
        fx, fy = hdufocusdata.shape
        # We want a standard focus image size that represent 0.2 degrees - which is the size of the focus fields.
        # However we want some flexibility in the sense that the pointing could be off by half a degree or so...
        # So we chop the image down to a degree by a degree
        # This speeds up the focus software.... we don't need to solve for EVERY star in a widefield image.
        fx_degrees = (fx * self.pixscale) /3600
        fy_degrees = (fy * self.pixscale) /3600

        crop_x=0
        crop_y=0


        if fx_degrees > 1.0:
            ratio_crop= 1/fx_degrees
            crop_x = int((fx - (ratio_crop * fx))/2)
        if fy_degrees > 1.0:
            ratio_crop= 1/fy_degrees
            crop_y = int((fy - (ratio_crop * fy))/2)

        if crop_x > 0 or crop_y > 0:
            if crop_x == 0:
                crop_x = 2
            if crop_y == 0:
                crop_y = 2
            # Make sure it is an even number for OSCs
            if (crop_x % 2) != 0:
                crop_x = crop_x+1
            if (crop_y % 2) != 0:
                crop_y = crop_y+1
            hdufocusdata = hdufocusdata[crop_x:-crop_x, crop_y:-crop_y]

        # # Just quick bin if an osc.
        # if self.is_osc:
        #     hdufocusdata=np.divide(block_reduce(hdufocusdata,2,func=np.sum),2)


        if self.is_osc:

            # Rapidly interpolate so that it is all one channel

            # Wipe out red channel
            hdufocusdata[::2, ::2]=np.nan
            # Wipe out blue channel
            hdufocusdata[1::2, 1::2]=np.nan

            # To fill the checker board, roll the array in all four directions and take the average
            # Which is essentially the bilinear fill without excessive math or not using numpy
            # It moves true values onto nans and vice versa, so makes an array of true values
            # where the original has nans and we use that as the fill
            #bilinearfill=np.mean( [ np.roll(hdufocusdata,1,axis=0), np.roll(hdufocusdata,-1,axis=0),np.roll(hdufocusdata,1,axis=1), np.roll(hdufocusdata,-1,axis=1)], axis=0 )
            #bilinearfill=np.divide(np.add( np.roll(hdufocusdata,1,axis=0), np.roll(hdufocusdata,-1,axis=0),np.roll(hdufocusdata,1,axis=1), np.roll(hdufocusdata,-1,axis=1),4))#, axis=0 )

            bilinearfill=np.roll(hdufocusdata,1,axis=0)
            bilinearfill=np.add(bilinearfill, np.roll(hdufocusdata,-1,axis=0))
            bilinearfill=np.add(bilinearfill, np.roll(hdufocusdata,1,axis=1))
            bilinearfill=np.add(bilinearfill, np.roll(hdufocusdata,-1,axis=1))
            bilinearfill=np.divide(bilinearfill,4)

            hdufocusdata[np.isnan(hdufocusdata)]=0
            bilinearfill[np.isnan(bilinearfill)]=0
            hdufocusdata=hdufocusdata+bilinearfill
            del bilinearfill




        fx, fy = hdufocusdata.shape        #
        #hdufocusdata=hdufocusdata-imageMedian
        tempstd=np.std(hdufocusdata)
        saturate = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]

        threshold=max(3* np.std(hdufocusdata[hdufocusdata < (5*tempstd)]),(200*self.pixscale)) # Don't bother with stars with peaks smaller than 100 counts per arcsecond
        googtime=time.time()
        list_of_local_maxima=localMax(hdufocusdata, threshold=threshold)
        #print ("Finding Local Maxima: " + str(time.time()-googtime))

        # Assess each point
        pointvalues=np.zeros([len(list_of_local_maxima),3],dtype=float)
        counter=0
        googtime=time.time()
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
                    #breakpoint()
                # Check it isn't just a dot
                if value_at_neighbours < (0.6*value_at_point):
                    #print ("BAH " + str(value_at_point) + " " + str(value_at_neighbours) )
                    pointvalues[counter][2]=np.nan
                # If not saturated and far away from the edge
                elif value_at_point < 0.8*saturate:
                    pointvalues[counter][2]=value_at_point
                else:
                    pointvalues[counter][2]=np.nan
            counter=counter+1
        #print ("Sorting out bad pixels from the mix: " + str(time.time()-googtime))


        # Trim list to remove things that have too many other things close to them.
        googtime=time.time()
        # remove nan rows
        pointvalues=pointvalues[~np.isnan(pointvalues).any(axis=1)]
        # reverse sort by brightness
        pointvalues=pointvalues[pointvalues[:,2].argsort()[::-1]]
        #From...... NOW
        #timer_for_bailing=time.time()
        # radial profile
        #fwhmlist=[]
        #sources=[]
        #photometry=[]
        #radius_of_radialprofile=(30)
        # The radius should be related to arcseconds on sky
        # And a reasonable amount - 12'
        try:
            radius_of_radialprofile=int(24/self.pixscale)
        except:
            # if pixelscale is not defined make it big
            radius_of_radialprofile=int(24/0.1)

        # Round up to nearest odd number to make a symmetrical array
        radius_of_radialprofile=int(radius_of_radialprofile // 2 *2 +1)
        halfradius_of_radialprofile=math.ceil(0.5*radius_of_radialprofile)
        #centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
        googtime=time.time()

        #amount=min(len(pointvalues),50)

        setup_timer=time.time()
        # Don't do them individually, set them up for multiprocessing
        focus_multiprocess=[]
        #for i in range(len(pointvalues)):
        #for i in range(min(len(pointvalues),200)):
        for i in range(min(len(pointvalues),200)):

            # # Don't take too long!
            # if ((time.time() - timer_for_bailing) > time_limit):# and good_radials > 20:
            #     print ("Time limit reached! Bailout!")
            #     break

            cx= int(pointvalues[i][0])
            cy= int(pointvalues[i][1])
            cvalue=hdufocusdata[int(cx)][int(cy)]


            #print (cvalue)

            try:
                #temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cx,cy))
                temp_array=hdufocusdata[cx-halfradius_of_radialprofile:cx+halfradius_of_radialprofile,cy-halfradius_of_radialprofile:cy+halfradius_of_radialprofile]
                #breakpoint()
                #temp_numpy=hdufocusdata[cx-radius_of_radialprofile:cx+radius_of_radialprofile,cy-radius_of_radialprofile:cy+radius_of_radialprofile]
            except:
                print(traceback.format_exc())
               # breakpoint()
            #crad=radial_profile(np.asarray(temp_array),[centre_of_radialprofile,centre_of_radialprofile])


            temptimer=time.time()
            #construct radial profile
            cut_x,cut_y=temp_array.shape
            cut_x_center=(cut_x/2)-1
            cut_y_center=(cut_y/2)-1
            radprofile=np.zeros([cut_x*cut_y,2],dtype=float)
            counter=0
            brightest_pixel_rdist=0
            brightest_pixel_value=0
            bailout=False
            for q in range(cut_x):
                # if bailout==True:
                #     break
                for t in range(cut_y):
                    #breakpoint()
                    r_dist=pow(pow((q-cut_x_center),2) + pow((t-cut_y_center),2),0.5)
                    if q-cut_x_center < 0:# or t-cut_y_center < 0:
                        r_dist=r_dist*-1
                    radprofile[counter][0]=r_dist
                    radprofile[counter][1]=temp_array[q][t]
                    if temp_array[q][t] > brightest_pixel_value:
                        brightest_pixel_rdist=r_dist
                        brightest_pixel_value=temp_array[q][t]
                    counter=counter+1
            # print ("radial dosn't take so long after all....")
            # print (time.time()-temptimer)




            #breakpoint()

            # If the brightest pixel is in the center-ish
            # then put it in contention
            if abs(brightest_pixel_rdist) <  max(3, 3/self.pixscale):
                #focus_multiprocess.append((cvalue, cx, cy, radprofile, temp_array,self.pixscale))
                focus_multiprocess.append((cvalue, cx, cy, radprofile, self.pixscale))
        #print ("Setup for multiprocess focus: " + str(time.time()-setup_timer))

        #Temporary just fur testing
        mptimer=time.time()
        fwhm_results=[]
        number_to_collect=max(16,2*os.cpu_count())
        for i in range(len(focus_multiprocess)):
            result=multiprocess_fast_gaussian_photometry(focus_multiprocess[i])
            if not np.isnan(result):
                fwhm_results.append(result)
                if len(fwhm_results) >= number_to_collect:
                    break
        # breakpoint()
        #print ("not multiprocess timer: " + str(time.time() - mptimer))

        # mptimer=time.time()
        # fwhm_results=[]
        # number_to_collect=max(16,2*os.cpu_count())
        # with Pool(os.cpu_count()) as pool:
        #     for result in pool.map(multiprocess_fast_gaussian_photometry, focus_multiprocess):
        #         if not np.isnan(result):
        #             fwhm_results.append(result)
        #             if len(fwhm_results) >= number_to_collect:
        #                 break
        # #print (fwhm_results)

        # print ("multiprocess timer: " + str(time.time() - mptimer))


        #print ("Extracting and Gaussianingx: " + str(time.time()-googtime))
                #breakpoint()
        #breakpoint()

        rfp = abs(bn.nanmedian(fwhm_results)) * 4.710
        rfr = rfp * self.pixscale
        rfs = np.nanstd(fwhm_results) * self.pixscale
        #print (rfr)
        #print (self.pixscale)
        if rfr < 1.0 or rfr > 12:
            rfr= np.nan
            rfp= np.nan
            rfs= np.nan

        #sepsky = imageMode
        fwhm_file={}
        fwhm_file['rfp']=str(rfp)
        fwhm_file['rfr']=str(rfr)
        fwhm_file['rfs']=str(rfs)
        fwhm_file['sky']=str(imageMedian)
        fwhm_file['sources']=str(len(fwhm_results))


        # If it is a focus image then it will get sent in a different manner to the UI for a jpeg
        # In this case, the image needs to be the 0.2 degree field that the focus field is made up of
        hdusmalldata = np.array(hdufocusdata)
        fx, fy = hdusmalldata.shape
        aspect_ratio= fx/fy

        focus_jpeg_size=0.2/(self.pixscale/3600)

        if focus_jpeg_size < fx:
            crop_width = (fx - focus_jpeg_size) / 2
        else:
            crop_width =2

        if focus_jpeg_size < fy:
            crop_height = (fy - (focus_jpeg_size / aspect_ratio) ) / 2
        else:
            crop_height = 2

        # Make sure it is an even number for OSCs
        if (crop_width % 2) != 0:
            crop_width = crop_width+1
        if (crop_height % 2) != 0:
            crop_height = crop_height+1

        crop_width = int(crop_width)
        crop_height = int(crop_height)

        if crop_width > 0 or crop_height > 0:
            hdusmalldata = hdusmalldata[crop_width:-crop_width, crop_height:-crop_height]

        hdusmalldata = hdusmalldata - np.min(hdusmalldata)

        stretched_data_float = mid_stretch_jpeg(hdusmalldata+1000)
        stretched_256 = 255 * stretched_data_float
        hot = np.where(stretched_256 > 255)
        cold = np.where(stretched_256 < 0)
        stretched_256[hot] = 255
        stretched_256[cold] = 0
        stretched_data_uint8 = stretched_256.astype("uint8")
        hot = np.where(stretched_data_uint8 > 255)
        cold = np.where(stretched_data_uint8 < 0)
        stretched_data_uint8[hot] = 255
        stretched_data_uint8[cold] = 0

        iy, ix = stretched_data_uint8.shape
        final_image = Image.fromarray(stretched_data_uint8)
        #draw = ImageDraw.Draw(final_image)

        #draw.text((0, 0), str(focus_position), (255))
        #draw.text((0, 0), str('MEANT TO BE FOCUS POSITION'), (255))


        # # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
        # if self.config["camera"][selfname]["settings"]["transpose_jpeg"]:
        #     final_image = final_image.transpose(Image.Transpose.TRANSPOSE)
        # if self.config["camera"][selfname]["settings"]['flipx_jpeg']:
        #     final_image = final_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        # if self.config["camera"][selfname]["settings"]['flipy_jpeg']:
        #     final_image = final_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        # if self.config["camera"][selfname]["settings"]['rotate180_jpeg']:
        #     final_image = final_image.transpose(Image.Transpose.ROTATE_180)
        # if self.config["camera"][selfname]["settings"]['rotate90_jpeg']:
        #     final_image = final_image.transpose(Image.Transpose.ROTATE_90)
        # if self.config["camera"][selfname]["settings"]['rotate270_jpeg']:
        #     final_image = final_image.transpose(Image.Transpose.ROTATE_270)


        if iy == ix:
            final_image = final_image.resize(
                (900, 900)
            )
        else:
            # if g_dev['obs'].config["camera"][g_dev['cam'].name]["settings"]["squash_on_x_axis"]:
            #     final_image = final_image.resize(

            #         (int(900 * iy / ix), 900)

            #     )
            # else:

            # There is no axis that is preferred?

            final_image = final_image.resize(

                (900, int(900 * iy / ix))

            )

        g_dev['cam'].current_focus_jpg=copy.deepcopy(final_image)


        del hdusmalldata
        del stretched_data_float
        del final_image

        return fwhm_file#, final_image

    # def in_line_quick_focus(self, hdufocusdata, im_path, text_name):

    #     googtime=time.time()
    #     # Check there are no nans in the image upon receipt
    #     # This is necessary as nans aren't interpolated in the main thread.
    #     # Fast next-door-neighbour in-fill algorithm
    #     #num_of_nans=np.count_nonzero(np.isnan(hdufocusdata))
    #     #x_size=hdufocusdata.shape[0]
    #     #y_size=hdufocusdata.shape[1]


    #     bkg = sep.Background(hdufocusdata, bw=32, bh=32, fw=3, fh=3)
    #     bkg.subfrom(hdufocusdata)

    #     # this is actually faster than np.nanmean
    #     imageMedian=bn.nanmedian(hdufocusdata)
    #     # Mop up any remaining nans
    #     hdufocusdata[np.isnan(hdufocusdata)] =imageMedian



    #     # Cut down focus image to central degree
    #     fx, fy = hdufocusdata.shape
    #     # We want a standard focus image size that represent 0.2 degrees - which is the size of the focus fields.
    #     # However we want some flexibility in the sense that the pointing could be off by half a degree or so...
    #     # So we chop the image down to a degree by a degree
    #     # This speeds up the focus software.... we don't need to solve for EVERY star in a widefield image.
    #     fx_degrees = (fx * self.pixscale) /3600
    #     fy_degrees = (fy * self.pixscale) /3600

    #     crop_x=0
    #     crop_y=0


    #     if fx_degrees > 1.0:
    #         ratio_crop= 1/fx_degrees
    #         crop_x = int((fx - (ratio_crop * fx))/2)
    #     if fy_degrees > 1.0:
    #         ratio_crop= 1/fy_degrees
    #         crop_y = int((fy - (ratio_crop * fy))/2)

    #     if crop_x > 0 or crop_y > 0:
    #         if crop_x == 0:
    #             crop_x = 2
    #         if crop_y == 0:
    #             crop_y = 2
    #         # Make sure it is an even number for OSCs
    #         if (crop_x % 2) != 0:
    #             crop_x = crop_x+1
    #         if (crop_y % 2) != 0:
    #             crop_y = crop_y+1
    #         hdufocusdata = hdufocusdata[crop_x:-crop_x, crop_y:-crop_y]

    #     # # Just quick bin if an osc.
    #     # if self.is_osc:
    #     #     hdufocusdata=np.divide(block_reduce(hdufocusdata,2,func=np.sum),2)


    #     if self.is_osc:

    #         # Rapidly interpolate so that it is all one channel

    #         # Wipe out red channel
    #         hdufocusdata[::2, ::2]=np.nan
    #         # Wipe out blue channel
    #         hdufocusdata[1::2, 1::2]=np.nan

    #         # To fill the checker board, roll the array in all four directions and take the average
    #         # Which is essentially the bilinear fill without excessive math or not using numpy
    #         # It moves true values onto nans and vice versa, so makes an array of true values
    #         # where the original has nans and we use that as the fill
    #         #bilinearfill=np.mean( [ np.roll(hdufocusdata,1,axis=0), np.roll(hdufocusdata,-1,axis=0),np.roll(hdufocusdata,1,axis=1), np.roll(hdufocusdata,-1,axis=1)], axis=0 )
    #         #bilinearfill=np.divide(np.add( np.roll(hdufocusdata,1,axis=0), np.roll(hdufocusdata,-1,axis=0),np.roll(hdufocusdata,1,axis=1), np.roll(hdufocusdata,-1,axis=1),4))#, axis=0 )

    #         bilinearfill=np.roll(hdufocusdata,1,axis=0)
    #         bilinearfill=np.add(bilinearfill, np.roll(hdufocusdata,-1,axis=0))
    #         bilinearfill=np.add(bilinearfill, np.roll(hdufocusdata,1,axis=1))
    #         bilinearfill=np.add(bilinearfill, np.roll(hdufocusdata,-1,axis=1))
    #         bilinearfill=np.divide(bilinearfill,4)

    #         hdufocusdata[np.isnan(hdufocusdata)]=0
    #         bilinearfill[np.isnan(bilinearfill)]=0
    #         hdufocusdata=hdufocusdata+bilinearfill
    #         del bilinearfill




    #     fx, fy = hdufocusdata.shape        #
    #     #hdufocusdata=hdufocusdata-imageMedian
    #     tempstd=np.std(hdufocusdata)
    #     saturate = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]

    #     threshold=max(3* np.std(hdufocusdata[hdufocusdata < (5*tempstd)]),(200*self.pixscale)) # Don't bother with stars with peaks smaller than 100 counts per arcsecond
    #     googtime=time.time()
    #     list_of_local_maxima=localMax(hdufocusdata, threshold=threshold)
    #     #print ("Finding Local Maxima: " + str(time.time()-googtime))

    #     # Assess each point
    #     pointvalues=np.zeros([len(list_of_local_maxima),3],dtype=float)
    #     counter=0
    #     googtime=time.time()
    #     for point in list_of_local_maxima:
    #         pointvalues[counter][0]=point[0]
    #         pointvalues[counter][1]=point[1]
    #         pointvalues[counter][2]=np.nan
    #         in_range=False
    #         if (point[0] > fx*0.1) and (point[1] > fy*0.1) and (point[0] < fx*0.9) and (point[1] < fy*0.9):
    #             in_range=True
    #         if in_range:
    #             value_at_point=hdufocusdata[point[0],point[1]]
    #             try:
    #                 value_at_neighbours=(hdufocusdata[point[0]-1,point[1]]+hdufocusdata[point[0]+1,point[1]]+hdufocusdata[point[0],point[1]-1]+hdufocusdata[point[0],point[1]+1])/4
    #             except:
    #                 print(traceback.format_exc())
    #                 #breakpoint()
    #             # Check it isn't just a dot
    #             if value_at_neighbours < (0.6*value_at_point):
    #                 #print ("BAH " + str(value_at_point) + " " + str(value_at_neighbours) )
    #                 pointvalues[counter][2]=np.nan
    #             # If not saturated and far away from the edge
    #             elif value_at_point < 0.8*saturate:
    #                 pointvalues[counter][2]=value_at_point
    #             else:
    #                 pointvalues[counter][2]=np.nan
    #         counter=counter+1
    #     #print ("Sorting out bad pixels from the mix: " + str(time.time()-googtime))


    #     # Trim list to remove things that have too many other things close to them.
    #     googtime=time.time()
    #     # remove nan rows
    #     pointvalues=pointvalues[~np.isnan(pointvalues).any(axis=1)]
    #     # reverse sort by brightness
    #     pointvalues=pointvalues[pointvalues[:,2].argsort()[::-1]]
    #     #From...... NOW
    #     #timer_for_bailing=time.time()
    #     # radial profile
    #     #fwhmlist=[]
    #     #sources=[]
    #     #photometry=[]
    #     #radius_of_radialprofile=(30)
    #     # The radius should be related to arcseconds on sky
    #     # And a reasonable amount - 12'
    #     radius_of_radialprofile=int(12/self.pixscale)
    #     # Round up to nearest odd number to make a symmetrical array
    #     radius_of_radialprofile=int(radius_of_radialprofile // 2 *2 +1)
    #     halfradius_of_radialprofile=math.ceil(0.5*radius_of_radialprofile)
    #     #centre_of_radialprofile=int((radius_of_radialprofile /2)+1)
    #     googtime=time.time()

    #     #amount=min(len(pointvalues),50)

    #     setup_timer=time.time()
    #     # Don't do them individually, set them up for multiprocessing
    #     focus_multiprocess=[]
    #     #for i in range(len(pointvalues)):
    #     #for i in range(min(len(pointvalues),200)):
    #     for i in range(min(len(pointvalues),200)):

    #         # # Don't take too long!
    #         # if ((time.time() - timer_for_bailing) > time_limit):# and good_radials > 20:
    #         #     print ("Time limit reached! Bailout!")
    #         #     break

    #         cx= int(pointvalues[i][0])
    #         cy= int(pointvalues[i][1])
    #         cvalue=hdufocusdata[int(cx)][int(cy)]


    #         #print (cvalue)

    #         try:
    #             #temp_array=extract_array(hdufocusdata, (radius_of_radialprofile,radius_of_radialprofile), (cx,cy))
    #             temp_array=hdufocusdata[cx-halfradius_of_radialprofile:cx+halfradius_of_radialprofile,cy-halfradius_of_radialprofile:cy+halfradius_of_radialprofile]
    #             #breakpoint()
    #             #temp_numpy=hdufocusdata[cx-radius_of_radialprofile:cx+radius_of_radialprofile,cy-radius_of_radialprofile:cy+radius_of_radialprofile]
    #         except:
    #             print(traceback.format_exc())
    #             #breakpoint()
    #         #crad=radial_profile(np.asarray(temp_array),[centre_of_radialprofile,centre_of_radialprofile])


    #         temptimer=time.time()
    #         #construct radial profile
    #         cut_x,cut_y=temp_array.shape
    #         cut_x_center=(cut_x/2)-1
    #         cut_y_center=(cut_y/2)-1
    #         radprofile=np.zeros([cut_x*cut_y,2],dtype=float)
    #         counter=0
    #         brightest_pixel_rdist=0
    #         brightest_pixel_value=0
    #         bailout=False
    #         for q in range(cut_x):
    #             # if bailout==True:
    #             #     break
    #             for t in range(cut_y):
    #                 #breakpoint()
    #                 r_dist=pow(pow((q-cut_x_center),2) + pow((t-cut_y_center),2),0.5)
    #                 if q-cut_x_center < 0:# or t-cut_y_center < 0:
    #                     r_dist=r_dist*-1
    #                 radprofile[counter][0]=r_dist
    #                 radprofile[counter][1]=temp_array[q][t]
    #                 if temp_array[q][t] > brightest_pixel_value:
    #                     brightest_pixel_rdist=r_dist
    #                     brightest_pixel_value=temp_array[q][t]
    #                 counter=counter+1
    #         # print ("radial dosn't take so long after all....")
    #         # print (time.time()-temptimer)




    #         #breakpoint()

    #         # If the brightest pixel is in the center-ish
    #         # then put it in contention
    #         if abs(brightest_pixel_rdist) < 4:
    #             #focus_multiprocess.append((cvalue, cx, cy, radprofile, temp_array,self.pixscale))
    #             focus_multiprocess.append((cvalue, cx, cy, radprofile, self.pixscale))
    #     print ("Setup for multiprocess focus: " + str(time.time()-setup_timer))

    #     # Temporary just to get binning right
    #     # for i in range(len(focus_multiprocess)):
    #     #     multiprocess_fast_gaussian_photometry(focus_multiprocess[i])
    #     #breakpoint()

    #     mptimer=time.time()
    #     fwhm_results=[]
    #     number_to_collect=max(8,os.cpu_count())
    #     with Pool(os.cpu_count()) as pool:
    #         for result in pool.map(multiprocess_fast_gaussian_photometry, focus_multiprocess):
    #             if not np.isnan(result):
    #                 fwhm_results.append(result)
    #                 if len(fwhm_results) >= number_to_collect:
    #                     break
    #     #print (fwhm_results)

    #     print ("multiprocess timer: " + str(time.time() - mptimer))


    #     print ("Extracting and Gaussianingx: " + str(time.time()-googtime))
    #             #breakpoint()
    #     #breakpoint()

    #     rfp = abs(bn.nanmedian(fwhm_results)) * 4.710
    #     rfr = rfp * self.pixscale
    #     rfs = np.nanstd(fwhm_results) * self.pixscale
    #     #print (rfr)
    #     #print (self.pixscale)
    #     if rfr < 1.0 or rfr > 12:
    #         rfr= np.nan
    #         rfp= np.nan
    #         rfs= np.nan

    #     #sepsky = imageMode
    #     fwhm_file={}
    #     fwhm_file['rfp']=str(rfp)
    #     fwhm_file['rfr']=str(rfr)
    #     fwhm_file['rfs']=str(rfs)
    #     fwhm_file['sky']=str(imageMedian)
    #     fwhm_file['sources']=str(len(fwhm_results))


    #     # If it is a focus image then it will get sent in a different manner to the UI for a jpeg
    #     # In this case, the image needs to be the 0.2 degree field that the focus field is made up of
    #     hdusmalldata = np.array(hdufocusdata)
    #     fx, fy = hdusmalldata.shape
    #     aspect_ratio= fx/fy

    #     focus_jpeg_size=0.2/(self.pixscale/3600)

    #     if focus_jpeg_size < fx:
    #         crop_width = (fx - focus_jpeg_size) / 2
    #     else:
    #         crop_width =2

    #     if focus_jpeg_size < fy:
    #         crop_height = (fy - (focus_jpeg_size / aspect_ratio) ) / 2
    #     else:
    #         crop_height = 2

    #     # Make sure it is an even number for OSCs
    #     if (crop_width % 2) != 0:
    #         crop_width = crop_width+1
    #     if (crop_height % 2) != 0:
    #         crop_height = crop_height+1

    #     crop_width = int(crop_width)
    #     crop_height = int(crop_height)

    #     if crop_width > 0 or crop_height > 0:
    #         hdusmalldata = hdusmalldata[crop_width:-crop_width, crop_height:-crop_height]

    #     hdusmalldata = hdusmalldata - np.min(hdusmalldata)

    #     stretched_data_float = mid_stretch_jpeg(hdusmalldata+1000)
    #     stretched_256 = 255 * stretched_data_float
    #     hot = np.where(stretched_256 > 255)
    #     cold = np.where(stretched_256 < 0)
    #     stretched_256[hot] = 255
    #     stretched_256[cold] = 0
    #     stretched_data_uint8 = stretched_256.astype("uint8")
    #     hot = np.where(stretched_data_uint8 > 255)
    #     cold = np.where(stretched_data_uint8 < 0)
    #     stretched_data_uint8[hot] = 255
    #     stretched_data_uint8[cold] = 0

    #     iy, ix = stretched_data_uint8.shape
    #     final_image = Image.fromarray(stretched_data_uint8)
    #     draw = ImageDraw.Draw(final_image)

    #     #draw.text((0, 0), str(focus_position), (255))
    #     draw.text((0, 0), str('MEANT TO BE FOCUS POSITION'), (255))
    #     try:
    #         final_image.save(im_path + text_name.replace('EX00.txt', 'EX10.jpg'))
    #     except:
    #         pass

    #     del hdusmalldata
    #     del stretched_data_float
    #     del final_image

    #     return fwhm_file#, final_image



    # #I assume we might be able to read the shutter state...

    # def query_Darkslide(self):

    # Note this is a thread!
    def camera_update_thread(self):


        #one_at_a_time = 0

        #Hooking up connection to win32 com focuser
        #win32com.client.pythoncom.CoInitialize()
    #     fl = win32com.client.Dispatch(
    #         win32com.client.pythoncom.CoGetInterfaceAndReleaseStream(g_dev['foc'].focuser_id, win32com.client.pythoncom.IID_IDispatch)
    # )

        win32com.client.pythoncom.CoInitialize()

        self.camera_update_wincom = win32com.client.Dispatch(self.driver)

        self.camera_update_wincom.Connect()
        #breakpoint()

        #self.camera_update_wincom.LinkEnabled = True
        #self.camera_update_wincom.Connected = True
        # try:
        #     self.pier_side = g_dev[
        #         "mnt"
        #     ].mount.sideOfPier  # 0 == Tel Looking West, is flipped.
        #     self.can_report_pierside = True
        # except:
        #     self.can_report_pierside = False

        # This stopping mechanism allows for threads to close cleanly.
        while True:

            # update every so often, but update rapidly if slewing.
            if (self.camera_update_timer < time.time() - self.camera_update_period) and not self.updates_paused:

                if self.camera_update_reboot:
                    win32com.client.pythoncom.CoInitialize()
                    self.camera_update_wincom = win32com.client.Dispatch(self.driver)

                    self.camera_update_wincom.Connect()

                    self.updates_paused=False
                    self.camera_update_reboot=False

                    # self.rapid_park_indicator=copy.deepcopy(self.mount_update_wincom.AtPark)
                    # self.currently_slewing=False
                    # #print (self.rapid_park_indicator)

                    # self.mount_updates=self.mount_updates + 1

                try:
                    self.theskyx_temperature= self.camera_update_wincom.Temperature, 999.9, 999.9

                    self.theskyx_cooleron= self.camera_update_wincom.RegulateTemperature

                    if self.theskyx_set_cooler_on==True:

                        self.camera_update_wincom.RegulateTemperature = 1
                        self.theskyx_set_cooler_on=False
                        # return (
                        #     self.camera_update_wincom.RegulateTemperature
                        # )

                    if self.theskyx_set_setpoint_trigger==True:
                        self.camera_update_wincom.TemperatureSetpoint = float(self.theskyx_set_setpoint_value)
                        self.camera_update_wincom.RegulateTemperature = 1
                        self.current_setpoint = self.theskyx_set_setpoint_value
                        #plog ("theskyx setpoint triggered: " + str(self.theskyx_set_setpoint_value))
                        self.theskyx_set_setpoint_trigger=False

                    if self.theskyx_abort_exposure_trigger==True:
                        self.camera_update_wincom.Abort()
                        self.theskyx_abort_exposure_trigger=False
                except:
                    plog ("non-permanent glitch out in the camera thread.")
                    plog(traceback.format_exc())


                # def _theskyx_set_setpoint(self, p_temp):
                #     self.camera_update_wincom.TemperatureSetpoint = float(p_temp)
                #     self.current_setpoint = p_temp
                #     return self.camera.TemperatureSetpoint

                #def _theskyx_setpoint(self):
                #    return self.camera_update_timer.TemperatureSetpoint

                # def _theskyx_cooler_power(self):
                #     return self.camera.CoolerPower

                # def _theskyx_heatsink_temp(self):
                #     return self.camera.HeatSinkTemperature



                # def _theskyx_set_cooler_on(self):
                #     self.camera.RegulateTemperature = True
                #     return (
                #         self.camera.RegulateTemperature
                #     )

                # def _theskyx_set_setpoint(self, p_temp):
                #     self.camera.TemperatureSetpoint = float(p_temp)
                #     self.current_setpoint = p_temp
                #     return self.camera.TemperatureSetpoint

                # def _theskyx_setpoint(self):
                #     return self.camera.TemperatureSetpoint
                # # Some things we don't do while slewing
                # if not self.currently_slewing:

                #     self.rapid_park_indicator=copy.deepcopy(self.mount_update_wincom.AtPark)
                #     #if self.can_report_pierside:
                #     self.rapid_pier_indicator=copy.deepcopy(self.mount_update_wincom.sideOfPier)
                #     self.current_tracking_state=self.mount_update_wincom.Tracking

                # self.right_ascension_directly_from_mount = copy.deepcopy(self.mount_update_wincom.RightAscension)
                # self.declination_directly_from_mount = copy.deepcopy(self.mount_update_wincom.Declination)

                # self.currently_slewing= self.mount_update_wincom.Slewing


                # self.mount_updates=self.mount_updates + 1
                # self.mount_update_timer=time.time()
                time.sleep(max(1,self.camera_update_period))
            else:
                time.sleep(max(1,self.camera_update_period))



    def post_processing_process(self):
        """

        This sends images through post-processing through one at a time.

        """

        one_at_a_time = 0
        while True:
            if (not self.post_processing_queue.empty()) and one_at_a_time == 0:
                one_at_a_time = 1
                #pre_upload = time.time()
                #breakpoint()
                payload = self.post_processing_queue.get(block=False)
                post_exposure_process(payload)
                self.post_processing_queue.task_done()

                one_at_a_time = 0
                time.sleep(2)
            else:
                time.sleep(2)



    # Patchable methods   NB These could be default ASCOM
    def _connected(self):
        plog("This is un-patched _connected method")
        return False

    def _connect(self, p_connect):
        plog("This is un-patched _connect method:  ", p_connect)
        return False

    def _setpoint(self):
        plog("This is un-patched cooler _setpoint method")
        return

    # The patches. Note these are essentially getter-setter/property constructs.

    def _theskyx_connected(self):
        return self.camera.LinkEnabled

    def _theskyx_connect(self, p_connect):
        self.camera.LinkEnabled = p_connect
        return self.camera.LinkEnabled

    def _theskyx_temperature(self):
        #return self.camera.Temperature, 999.9, 999.9
        return self.theskyx_temperature

    def _theskyx_cooler_power(self):
        return self.camera.CoolerPower

    def _theskyx_heatsink_temp(self):
        return self.camera.HeatSinkTemperature

    def _theskyx_cooler_on(self):
        #return self.camera.RegulateTemperature
        return self.theskyx_cooleron

    def _theskyx_set_cooler_on(self):
        self.theskyx_set_cooler_on=True
        return True
        # self.camera.RegulateTemperature = True
        # return (
        #     self.camera.RegulateTemperature
        # )

    def _theskyx_set_setpoint(self, p_temp):

        self.theskyx_set_setpoint_trigger=True
        self.theskyx_set_setpoint_value= float(p_temp)
        self.current_setpoint=float(p_temp)
        return float(p_temp)
        #self.camera.TemperatureSetpoint = float(p_temp)
        #self.current_setpoint = p_temp
        #return self.camera.TemperatureSetpoint

    def _theskyx_setpoint(self):
        #return self.camera.TemperatureSetpoint
        return self.theskyx_set_setpoint_value

    def theskyx_async_expose(self):
        self.async_exposure_lock=True
        tempcamera = win32com.client.Dispatch(self.driver)
        tempcamera.Connect()

        tempcamera.ExposureTime = self.theskyxExposureTime
        #if bias_dark_or_light_type_frame == 'dark':
        tempcamera.Frame = self.theskyxFrame
        #elif bias_dark_or_light_type_frame == 'bias':
        #    self.camera.Frame = 2
        #else:
        #    self.camera.Frame = 1


        try:
            tempcamera.TakeImage()
        except:
            if 'Process aborted.' in str(traceback.format_exc()):
                plog ("Image aborted. This functioning is ok. Traceback just for checks that it is working.")
                #plog(traceback.format_exc())
            elif 'SBIG driver' in str(traceback.format_exc()):
                plog(traceback.format_exc())
                plog ("Killing and rebooting TheSKYx and seeing if it will continue on after SBIG fail")
                g_dev['seq'].kill_and_reboot_theskyx(g_dev['mnt'].return_right_ascension(),g_dev['mnt'].return_declination())
            else:
                plog(traceback.format_exc())
                plog("MTF hunting this error")
                #breakpoint()
        while not tempcamera.IsExposureComplete:
            self.theskyxIsExposureComplete=False
            time.sleep(0.01)
        self.theskyxIsExposureComplete=True
        self.theskyxLastImageFileName=tempcamera.LastImageFileName

        tempcamera.ShutDownTemperatureRegulationOnDisconnect = False

        self.async_exposure_lock=False

    def _theskyx_expose(self, exposure_time, bias_dark_or_light_type_frame):
        self.theskyxExposureTime = exposure_time
        if bias_dark_or_light_type_frame == 'dark':
            self.theskyxFrame = 3
        elif bias_dark_or_light_type_frame == 'bias':
            self.theskyxFrame = 2
        else:
            self.theskyxFrame = 1
        self.theskyxIsExposureComplete=False
        thread=threading.Thread(target=self.theskyx_async_expose)
        thread.daemon=True
        thread.start()

    def _theskyx_stop_expose(self):
        try:
            #self.camera.Abort()
            self.theskyx_abort_exposure_trigger=True
        except:
            plog(traceback.format_exc())
        g_dev['cam'].expresult = {}
        g_dev['cam'].expresult["stopped"] = True
        return

    def _theskyx_imageavailable(self):
        #plog(self.camera.IsExposureComplete)
        try:
            #return self.camera.IsExposureComplete
            return self.theskyxIsExposureComplete
        except:
            if 'Process aborted.' in str(traceback.format_exc()):
                plog ("Image isn't available because the command was aborted.")
            else:
                plog(traceback.format_exc())

    def _theskyx_getImageArray(self):
        imageTempOpen=fits.open(self.theskyxLastImageFileName, uint=False)[0].data.astype("float32")
        try:
            os.remove(self.theskyxLastImageFileName)
        except Exception as e:
            plog ("Could not remove theskyx image file: ",e)
        return imageTempOpen

    def _maxim_connected(self):
        return self.camera.LinkEnabled

    def _maxim_connect(self, p_connect):
        self.camera.LinkEnabled = p_connect
        return self.camera.LinkEnabled

    def _maxim_temperature(self):
        return self.camera.Temperature, 999.9, 999.9

    def _maxim_cooler_power(self):
        return self.camera.CoolerPower

    def _maxim_heatsink_temp(self):
        return self.camera.HeatSinkTemperature

    def _maxim_cooler_on(self):
        return (
            self.camera.CoolerOn
        )

    def _maxim_set_cooler_on(self):
        self.camera.CoolerOn = True
        return (
            self.camera.CoolerOn
        )

    def _maxim_set_setpoint(self, p_temp):
        self.camera.TemperatureSetpoint = float(p_temp)
        self.current_setpoint = p_temp
        return self.camera.TemperatureSetpoint

    def _maxim_setpoint(self):
        return self.camera.TemperatureSetpoint

    def _maxim_expose(self, exposure_time, bias_dark_or_light_type_frame):
        if bias_dark_or_light_type_frame == 'bias' or bias_dark_or_light_type_frame == 'dark':
            imtypeb=0
        else:
            imtypeb=1
        self.camera.Expose(exposure_time, imtypeb)

    def _maxim_stop_expose(self):
        self.camera.AbortExposure()
        g_dev['cam'].expresult = {}
        g_dev['cam'].expresult["stopped"] = True

    def _maxim_imageavailable(self):
        return self.camera.ImageReady

    def _maxim_getImageArray(self):
        return np.asarray(self.camera.ImageArray)

    def _ascom_connected(self):
        return self.camera.Connected

    def _ascom_imageavailable(self):
        return self.camera.ImageReady

    def _ascom_connect(self, p_connect):
        self.camera.Connected = p_connect
        return self.camera.Connected

    def _ascom_temperature(self):

        try:
            temptemp=self.camera.CCDTemperature
        except:
            plog ("failed at getting the CCD temperature")
            temptemp=999.9
        return temptemp, 999.9, 999.9

    def _ascom_cooler_on(self):
        return (
            self.camera.CoolerOn
        )  # NB NB NB This would be a good place to put a warming protector

    def _ascom_set_cooler_on(self):
        self.camera.CoolerOn = True
        return self.camera.CoolerOn

    def _ascom_set_setpoint(self, p_temp):
        if self.camera.CanSetCCDTemperature:
            self.camera.SetCCDTemperature = float(p_temp)
            self.current_setpoint = p_temp
            return self.camera.SetCCDTemperature
        else:
            plog("Camera cannot set cooling temperature.")
            return p_temp

    def _ascom_setpoint(self):
        if self.camera.CanSetCCDTemperature:
            return self.camera.SetCCDTemperature
        else:
            plog("Camera cannot set cooling temperature: Using 10.0C")
            return 10.0

    def _ascom_expose(self, exposure_time, bias_dark_or_light_type_frame):

        if bias_dark_or_light_type_frame == 'bias' or bias_dark_or_light_type_frame == 'dark':
            imtypeb=0
        else:
            imtypeb=1

        self.camera.StartExposure(exposure_time, imtypeb)

    def _ascom_stop_expose(self):
        self.camera.StopExposure()  # ASCOM also has an AbortExposure method.
        g_dev['cam'].expresult = {}
        g_dev['cam'].expresult["stopped"] = True

    def _ascom_getImageArray(self):
        return np.asarray(self.camera.ImageArray)


    def _qhyccd_connected(self):
        print ("MTF still has to connect QHY stuff")
        return True

    def _qhyccd_imageavailable(self):
        #print ("QHY CHECKING FOR IMAGE AVAILABLE - DOESN'T SEEM TO BE IMPLEMENTED! - MTF")
        #print ("AT THE SAME TIME THE READOUT IS SO RAPID, THIS FUNCTION IS SORTA MEANINGLESS FOR THE QHY.")
        if self.substacker and not self.substacker_available:
            return False
        else:
            return True

    def _qhyccd_connect(self, p_connect):
        #self.camera.Connected = p_connect
        #print ("QHY doesn't have an obvious - IS CONNECTED - function")

        return True

    def _qhyccd_temperature(self):
        try:

            temptemp=qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP)
            humidity = qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CAM_HUMIDITY)
            pressure = qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CAM_PRESSURE)
            pwm = qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'],     qhycam.CONTROL_CURPWM)
            manual_pwm = qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_MANULPWM)
            #print(' QHY pwm:  ', pwm)
        except:
            print ("failed at getting the CCD temperature, humidity or pressure.")
            temptemp=999.9
        return temptemp, humidity, pressure

    def _qhyccd_cooler_on(self):
        #print ("QHY DOESN'T HAVE AN IS COOLER ON METHOD)
        #breakpoint()
        #temptemp=qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_COOLER,c_double(self.setpoint))
        return True

    def _qhyccd_set_cooler_on(self):
        temptemp=qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_COOLER,c_double(self.current_setpoint))
        return True

    def _qhyccd_set_setpoint(self, p_temp):
        temptemp=qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_COOLER,c_double(p_temp))
        self.current_setpoint = p_temp
        return p_temp

    def _qhyccd_setpoint(self):
        try:
            temptemp=qhycam.so.GetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP)
        except:
            print ("failed at getting the CCD temperature")
            temptemp=999.9
        return temptemp

    # def _qhyccd_special_subthread_expose(self, exposure_time, bias_dark_or_light_type_frame):
    #     success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(exposure_time*1000*1000))
    #     qhycam.so.ExpQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'])

    # def _qhyccd_special_subthread_prepandalign(self, reference_image, alignment_image):


    #     print ()

    def qhy_substacker_thread(self, exposure_time):

        #N_of_substacks = 10
        exp_of_substacks = 10
        readout_estimate_holder=[]
        N_of_substacks = int(exposure_time / exp_of_substacks)
        #readouts=0


        is_osc=self.config["camera"][self.name]["settings"]['is_osc']



        self.sub_stacker_midpoints=[]



        #print ("subexposing")
        for subexposure in range(N_of_substacks+1):
            #print (subexposure)

            # Check there hasn't been a cancel sent through
            if g_dev["obs"].stop_all_activity:
                plog ("stop_all_activity cancelling out of camera exposure")
                # Nsmartstack=1
                # sskcounter=2
                # # expresult["error"] = True
                # # expresult["stopped"] = True
                # g_dev["obs"].exposure_halted_indicator =False
                # self.currently_in_smartstack_loop=False
                #self.running_an_exposure_set = False
                self.shutter_open=False
                return
            if g_dev["obs"].exposure_halted_indicator:
                # expresult["error"] = True
                # expresult["stopped"] = True
                # g_dev["obs"].exposure_halted_indicator =False
                # plog ("Exposure Halted Indicator On. Cancelling Exposure.")
                #self.running_an_exposure_set = False
                self.shutter_open=False
                return

            exposure_timer=time.time()
            # If it is the first exposure, then just take the exposure. Same with the second as the first one is the reference.

            if subexposure == 0 or subexposure == 1:
                plog ("Collecting subexposure " + str(subexposure+1))

                success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(exp_of_substacks*1000*1000))
                if subexposure == 0 :
                    self.substack_start_time=time.time()
                    # Load in the flat to be used during sub_stacker_array
                    no_flat=False
                    try:
                        temporary_flat_in_memory=np.load(g_dev['cam'].flatFiles[str(g_dev['cam'].current_filter + "_bin" + str(1))])
                    except:
                        no_flat=True
                        plog ("Could not find flat for this substack")
                    #sub_stacker_array=np.zeros((self.imagesize_x,self.imagesize_y,N_of_substacks), dtype=np.float32)
                self.sub_stacker_midpoints.append(copy.deepcopy(time.time() + (0.5*exp_of_substacks)))
                qhycam.so.ExpQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'])
                exposure_timer=time.time()


                # if during first exposure, create memmap disk array
                temporary_substack_directory=self.local_calibration_path + "subsstacks/" + str(time.time()).replace('.','')
                if not os.path.exists(temporary_substack_directory):
                    os.makedirs(temporary_substack_directory)

                sub_stacker_array = np.memmap(temporary_substack_directory + '/tempfile', dtype='float32', mode= 'w+', shape = (self.imagesize_x,self.imagesize_y,N_of_substacks))


                


                if subexposure == 1:
                    #print ("Flat,DarkBiasing reference frame")
                    # De-biasdark sub_stack array

                    # hdufocus = fits.PrimaryHDU()
                    # hdufocus.data = sub_stacker_array[:,:,0]
                    # #hdufocus.header = googimage[0].header
                    # hdufocus.writeto('referenceframe.fits', overwrite=True, output_verify='silentfix')
                    try:
                        sub_stacker_array[:,:,0]=sub_stacker_array[:,:,0] - g_dev['cam'].darkFiles['tensec_exposure_biasdark']
                    except:
                        plog ("Couldn't biasdark substack")
                        pass
                    # Flat field sub stack array
                    #plog ("Flatting 0")
                    if not no_flat:
                        try:
                            # if self.config['camera'][self.name]['settings']['hold_flats_in_memory']:
                            #     sub_stacker_array[:,:,0] = np.divide(sub_stacker_array[:,:,0], g_dev['cam'].flatFiles[g_dev['cam'].current_filter])
                            # else:
                            sub_stacker_array[:,:,0] = np.divide(sub_stacker_array[:,:,0], temporary_flat_in_memory)
                        except:
                            plog ("couldn't flat field substack")
                            pass
                    else:
                        plog ("couldn't flat field substack")
                        pass
                    # Bad pixel map sub stack array
                    try:
                        sub_stacker_array[:,:,0][g_dev['cam'].bpmFiles[str(1)]] = np.nan
                    except:
                        plog ("Couldn't badpixel substack")
                        pass

                    # hdufocus = fits.PrimaryHDU()
                    # hdufocus.data = sub_stacker_array[:,:,0]
                    # #hdufocus.header = googimage[0].header
                    # hdufocus.writeto('referenceframecalibrated.fits', overwrite=True, output_verify='silentfix')




                    de_nanned_reference_frame=copy.deepcopy(sub_stacker_array[:,:,0])
                    if is_osc:
                        # Wipe out red channel
                        de_nanned_reference_frame[::2, ::2]=np.nan
                        # Wipe out blue channel
                        de_nanned_reference_frame[1::2, 1::2]=np.nan


                    # Cut down image to central thousand by thousand patch to align
                    fx, fy = de_nanned_reference_frame.shape
                    crop_x= int(0.5*fx) -1000
                    crop_y= int(0.5*fy) -1000
                    # crop_x=100
                    # crop_y=100
                    de_nanned_reference_frame = de_nanned_reference_frame[crop_x:-crop_x, crop_y:-crop_y]
                    

                    #tempnan=copy.deepcopy(sub_stacker_array[:,:,subexposure-1])
                    #de_nanned_reference_frame[np.isnan(de_nanned_reference_frame)] =imageMode

                    denan_mask=copy.deepcopy(de_nanned_reference_frame)
                    #denan_median=bn.nanmedian(denan_mask)
                    imageMode=2.5 * bn.nanmedian(de_nanned_reference_frame) - 1.5 * bn.nanmean(de_nanned_reference_frame)
                    denan_mask[np.isnan(denan_mask)] = False
                    denan_mask[denan_mask <= imageMode] = False
                    denan_mask[denan_mask > imageMode] = True
                    denan_mask=denan_mask.astype('bool')

            # For each further exposure, align the previous subexposure while exposing the next exposure
            # Do this through separate threads. The alignment should be faster than the exposure
            # So we don't need to get too funky, just two threads that wait for each other.
            else:


                if not subexposure == (N_of_substacks):
                    # Fire off an exposure.
                    plog ("Collecting subexposure " + str(subexposure+1))
                    qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(exp_of_substacks*1000*1000))
                    self.expected_endpoint_of_substack_exposure=time.time() + exp_of_substacks
                    self.sub_stacker_midpoints.append(copy.deepcopy(time.time() + (0.5*exp_of_substacks)))
                    qhycam.so.ExpQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'])

                    exposure_timer=time.time()
                # While the exposure is happening prep align and stack the previous exposure.
                #print ("Processing " +str(subexposure))


                # hdufocus = fits.PrimaryHDU()
                # hdufocus.data = sub_stacker_array[:,:,subexposure-1]
                # #hdufocus.header = googimage[0].header
                # hdufocus.writeto(str(subexposure-1) + 'frame.fits', overwrite=True, output_verify='silentfix')

                #rolltimer=time.time()
                try:
                    # De-biasdark sub_stack array
                    sub_stacker_array[:,:,subexposure-1]=sub_stacker_array[:,:,subexposure-1] - g_dev['cam'].darkFiles['tensec_exposure_biasdark']
                except:
                    plog ("couldn't biasdark substack")
                    pass


                # Flat field sub stack array
                #plog ("Flatting " + str(subexposure-1))
                try:
                    # if self.config['camera'][self.name]['settings']['hold_flats_in_memory']:
                    #     sub_stacker_array[:,:,subexposure-1] = np.divide(sub_stacker_array[:,:,subexposure-1], g_dev['cam'].flatFiles[g_dev['cam'].current_filter])
                    # else:
                    sub_stacker_array[:,:,subexposure-1] = np.divide(sub_stacker_array[:,:,subexposure-1], temporary_flat_in_memory)
                except:
                    plog ("couldn't flat field substack")
                    pass

                # Bad pixel map sub stack array
                try:
                    sub_stacker_array[:,:,subexposure-1][g_dev['cam'].bpmFiles[str(1)]] = np.nan

                except:
                    plog ("couldn't badpixel field substack")
                    pass
                # hdufocus = fits.PrimaryHDU()
                # hdufocus.data = sub_stacker_array[:,:,subexposure-1]
                # #hdufocus.header = googimage[0].header
                # hdufocus.writeto(str(subexposure-1) + 'framecalibrated.fits', overwrite=True, output_verify='silentfix')
                #print ("Calibrating: " + str(time.time()-rolltimer))

                # Make a tempfile that has nan's medianed out


                # Using the nan'ed file, calculate the shift
                #rolltimer=time.time()
                tempnan_mask=copy.deepcopy(sub_stacker_array[:,:,subexposure-1])

                if is_osc:
                    # Wipe out red channel
                    tempnan_mask[::2, ::2]=np.nan
                    # Wipe out blue channel
                    tempnan_mask[1::2, 1::2]=np.nan


                # Cut down image to central thousand by thousand patch to align
                tempnan_mask= tempnan_mask[crop_x:-crop_x, crop_y:-crop_y]
                #imageMode=bn.nanmedian(tempnan)
                #tempnan[np.isnan(tempnan)] =imageMode

                #de_nanned_reference_frame[de_nanned_reference_frame < bn.nanmedian(de_nanned_reference_frame)] = np.nan

                #tempnan_mask=copy.deepcopy(tempnan)
                tempnan_mode=2.5 * bn.nanmedian(de_nanned_reference_frame) - 1.5 * bn.nanmean(de_nanned_reference_frame)
                tempnan_mask[np.isnan(tempnan_mask)] = False
                tempnan_mask[tempnan_mask <= tempnan_mode] = False
                tempnan_mask[tempnan_mask > tempnan_mode] = True
                tempnan_mask=tempnan_mask.astype('bool')

                #breakpoint()
                
                # denan_mask=copy.deepcopy(de_nanned_reference_frame)
                # #denan_median=bn.nanmedian(denan_mask)
                # imageMode=2.5 * bn.nanmedian(de_nanned_reference_frame) - 1.5 * bn.nanmean(de_nanned_reference_frame)
                # denan_mask[np.isnan(denan_mask)] = False
                # denan_mask[denan_mask <= imageMode] = False
                # denan_mask[denan_mask > imageMode] = True
                # denan_mask=denan_mask.astype('bool')
                

                imageshift = phase_cross_correlation(de_nanned_reference_frame, sub_stacker_array[:,:,subexposure-1][crop_x:-crop_x, crop_y:-crop_y], reference_mask=denan_mask, moving_mask=tempnan_mask)
                #imageshift = phase_cross_correlation(de_nanned_reference_frame, sub_stacker_array[:,:,subexposure-1][100:-100, 100:-100], reference_mask=denan_mask, moving_mask=tempnan_mask)



                #imageshift, error, diffphase = phase_cross_correlation(de_nanned_reference_frame, tempnan)
                #print ("Shift: " + str(time.time()-rolltimer))
                #del tempnan
                print (imageshift)

                if len(imageshift) == 3:
                    imageshift=imageshift[0]

                try:
                    if abs(imageshift[0]) > 0:
                        # print ("X shifter")
                        #if imageshift[0]
                        imageshiftabs=int(abs(imageshift[0]))
                        # If it is an OSC, it needs to be an even number
                        if is_osc:
                            if (imageshiftabs & 0x1) == 1:
                                imageshiftabs=imageshiftabs+1


                        if imageshift[0] > 0:
                            imageshiftsign = 1
                        else:
                            imageshiftsign = -1

                        sub_stacker_array[:,:,subexposure-1]=np.roll(sub_stacker_array[:,:,subexposure-1], imageshiftabs*imageshiftsign, axis=0)
                        # print ("Roll: " + str(time.time()-rolltimer))

                    # rolltimer=time.time()
                    if abs(imageshift[1]) > 0:
                        # print ("Y shifter")
                        # print (int(imageshift[1]))

                        imageshiftabs=int(abs(imageshift[1]))

                        # If it is an OSC, it needs to be an even number
                        if is_osc:
                            if (imageshiftabs & 0x1) == 1:
                                imageshiftabs=imageshiftabs+1

                        if imageshift[1] > 0:
                            imageshiftsign = 1
                        else:
                            imageshiftsign = -1


                        sub_stacker_array[:,:,subexposure-1]=np.roll(sub_stacker_array[:,:,subexposure-1], imageshiftabs*imageshiftsign, axis=1)

                except:
                    plog(traceback.format_exc())
                    breakpoint()

                del tempnan_mask


                # # rolltimer=time.time()
                # # roll the original array around by the shift
                # if abs(imageshift[0]) > 0:
                #     # print ("X shifter")
                #     # print (int(imageshift[0]))
                #     sub_stacker_array[:,:,subexposure-1]=np.roll(sub_stacker_array[:,:,subexposure-1], int(imageshift[0]), axis=0)
                #     # print ("Roll: " + str(time.time()-rolltimer))

                # # rolltimer=time.time()
                # if abs(imageshift[1]) > 0:
                #     # print ("Y shifter")
                #     # print (int(imageshift[1]))
                #     sub_stacker_array[:,:,subexposure-1]=np.roll(sub_stacker_array[:,:,subexposure-1], int(imageshift[1]), axis=1)
                #     # print ("Roll: " + str(time.time()-rolltimer))

                # from scipy.ndimage import shift

                # rolltimer=time.time()
                # if abs(imageshift[0]) > 0 or abs(imageshift[1]) > 0:
                #     scipyroll=shift(sub_stacker_array[:,:,subexposure-1])



                #print ("Time taken for aligning: " + str(time.time()-exposure_timer))


            #print ("too many readouts?")
            #print (subexposure)
            #print (N_of_substacks)
            if not subexposure == (N_of_substacks):
                #readouts=readouts+1
                #print ("readouts " +str(readouts))
                while (time.time() - exposure_timer) < exp_of_substacks:
                    #print ("Watiing for exposure to finish")
                    time.sleep(0.005)

                # If this is the last exposure of the set of subexposures, then report shutter closed
                if subexposure == (N_of_substacks-1):
                    self.shutter_open=False

            #if not subexposure == (N_of_substacks):
                # READOUT FROM THE QHY

                image_width_byref = c_uint32()
                image_height_byref = c_uint32()
                bits_per_pixel_byref = c_uint32()
                time_before_last_substack_readout=time.time()
                success = qhycam.so.GetQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'],
                                                      byref(image_width_byref),
                                                      byref(image_height_byref),
                                                      byref(bits_per_pixel_byref),
                                                      byref(qhycam.camera_params[qhycam_id]['channels']),
                                                      byref(qhycam.camera_params[qhycam_id]['prev_img_data']))

                image = np.ctypeslib.as_array(qhycam.camera_params[qhycam_id]['prev_img_data'])
                time_after_last_substack_readout=time.time()

                #plog ("readout time: " + str(time_after_last_substack_readout - time_before_last_substack_readout))
                readout_estimate_holder.append(time_after_last_substack_readout - time_before_last_substack_readout)



                sub_stacker_array[:,:,subexposure] = np.reshape(image[0:(self.imagesize_x*self.imagesize_y)], (self.imagesize_x, self.imagesize_y))




                #print ("Collected " +str(subexposure+1))




            #sub_stacker_array[:,:,subexposure] = self._getImageArray()

        del denan_mask
        del de_nanned_reference_frame

        # Once collected and done, nanmedian the array into the single image

        self.readout_estimate= np.median(np.array(readout_estimate_holder))

        #temptimer=time.time()
        sub_stacker_array=bn.nanmedian(sub_stacker_array, axis=2) * N_of_substacks
        #print ("Stacktime: " + str(time.time()-temptimer))
        self.sub_stack_hold = sub_stacker_array

        #self.substack_midpoint_time=(self.substack_start_time + expected_endpoint_of_substack_exposure) / 2

        del sub_stacker_array
        self.substacker_available=True
        self.shutter_open=False

    def _qhyccd_expose(self, exposure_time, bias_dark_or_light_type_frame):



        self.substacker_available=False

        #breakpoint()


        if bias_dark_or_light_type_frame == 'bias':
            exposure_time = 40 /1000/1000 # shortest requestable exposure time

        if not self.substacker:
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(exposure_time*1000*1000))
            qhycam.so.ExpQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'])
        else:


            thread=threading.Thread(target=self.qhy_substacker_thread, args=(exposure_time,))
            thread.daemon=True
            thread.start()





                    #sub_stacker_array[:,:,subexposure-1]=_qhyccd_special_subthread_align(sub_stacker_array[:,:,0], sub_stacker_array[:,:,subexposure-1])



    def _qhyccd_stop_expose(self):
        expresult = {}
        expresult["stopped"] = True
        self.shutter_open=False
        try:
            qhycam.so.CancelQHYCCDExposingAndReadout(qhycam.camera_params[qhycam_id]['handle'])
        except:
            plog(traceback.format_exc())
            #print (success)


    def _qhyccd_getImageArray(self):

        if self.substacker:
            return self.sub_stack_hold
        else:
            image_width_byref = c_uint32()
            image_height_byref = c_uint32()
            bits_per_pixel_byref = c_uint32()

            #qhycommand=time.time()
            time_before_readout=time.time()
            success = qhycam.so.GetQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'],
                                                  byref(image_width_byref),
                                                  byref(image_height_byref),
                                                  byref(bits_per_pixel_byref),
                                                  byref(qhycam.camera_params[qhycam_id]['channels']),
                                                  byref(qhycam.camera_params[qhycam_id]['prev_img_data']))

            #print (time.time() - qhycommand)

            image = np.ctypeslib.as_array(qhycam.camera_params[qhycam_id]['prev_img_data'])
            time_after_readout=time.time()

            #plog ("readout time: " + str(time_after_readout - time_before_readout))
            self.readout_estimate= time_after_readout - time_before_readout
            #npreshaprecommand=time.time()
            #image = np.reshape(image[0:(self.imagesize_x*self.imagesize_y)], (self.imagesize_x, self.imagesize_y))

            return np.reshape(image[0:(self.imagesize_x*self.imagesize_y)], (self.imagesize_x, self.imagesize_y))
            #return np.asarray(image)
            #return image

    def wait_for_slew(self):
        """
        A function called when the code needs to wait for the telescope to stop slewing before undertaking a task.
        """
        if not g_dev['obs'].mountless_operation:
            try:
                if not g_dev['mnt'].rapid_park_indicator:
                    movement_reporting_timer = time.time()
                    while g_dev['mnt'].return_slewing():
                        #g_dev['mnt'].currently_slewing= True
                        if time.time() - movement_reporting_timer > g_dev['obs'].status_interval:
                            plog('m>')
                            movement_reporting_timer = time.time()
                            if not g_dev['obs'].currently_updating_status and g_dev['obs'].update_status_queue.empty():
                                g_dev['mnt'].get_mount_coordinates()
                                g_dev['obs'].request_update_status(mount_only=True)#, dont_wait=True)
                            #g_dev['obs'].update_status(mount_only=True, dont_wait=True)
                    #g_dev['mnt'].currently_slewing= False
                    # Then wait for slew_time to settle
                    time.sleep(g_dev['mnt'].wait_after_slew_time)

            except Exception as e:
                plog("Motion check faulted.")
                plog(traceback.format_exc())
                if 'pywintypes.com_error' in str(e):
                    plog ("Mount disconnected. Recovering.....")
                    time.sleep(5)
                    g_dev['mnt'].reboot_mount()
                else:
                    pass
            return


    def create_simple_autosave(
        self,
        exp_time=0,
        img_type=0,
        speed=0,
        suffix="",
        repeat=1,
        readout_mode="Normal",
        filter_name="W",
        enabled=1,
        column=1,
    ):
        # Creates a valid Maxium Autosave file.
        exp_time = round(abs(float(exp_time)), 3)
        if img_type > 3:
            img_type = 0
        repeat = abs(int(repeat))
        if repeat < 1:
            repeat = 1
        binning = abs(int(1))
        if filter_name == "":
            filter_name = "w"
        proto_file = open(self.camera_path + "seq/ptr_proto.seq")
        proto = proto_file.readlines()
        proto_file.close()

        if column == 1:
            proto[51] = proto[51][:9] + str(img_type) + proto[51][10:]
            proto[50] = proto[50][:9] + str(exp_time) + proto[50][12:]
            proto[48] = proto[48][:12] + str(suffix) + proto[48][12:]
            proto[47] = proto[47][:10] + str(speed) + proto[47][11:]
            proto[31] = proto[31][:11] + str(repeat) + proto[31][12:]
            proto[29] = proto[29][:17] + readout_mode + proto[29][23:]
            proto[13] = proto[13][:12] + filter_name + proto[13][13:]
            proto[10] = proto[10][:12] + str(enabled) + proto[10][13:]
            proto[1] = proto[1][:12] + str(binning) + proto[1][13:]
        seq_file = open(self.camera_path + "seq/ptr_mrc.seq", "w")
        for item in range(len(proto)):
            seq_file.write(proto[item])
        seq_file.close()

    def get_status(self):
        status = {}
        status["active_camera"] = self.name
        if self.config["camera"][self.name]["settings"]["has_darkslide"]:
            status["darkslide"] = self.darkslide_state
        else:
            status["darkslide"] = "unknown"

        cam_stat = self.config['camera'][self.name]['name'] + " connected." # self.camera.CameraState
        status[
            "status"
        ] = cam_stat  # The state could be expanded to be more meaningful. for instance report TEC % TEmp, temp setpoint...
        return status

    def parse_command(self, command):

        req = command["required_params"]
        opt = command["optional_params"]
        action = command["action"]
        #breakpoint()
        self.user_id = command["user_id"]
        if self.user_id != self.last_user_id:
            self.last_user_id = self.user_id
        self.user_name = command["user_name"]

        if (
            "object_name" in opt
        ):
            if opt["object_name"] == "":
                opt["object_name"] = "Unspecified"
            plog("Target Name:  ", opt["object_name"])
        else:
            opt["object_name"] = "Unspecified"
            plog("Target Name:  ", opt["object_name"])
        if self.user_name != self.last_user_name:
            self.last_user_name = self.user_name
        if action == "expose":# and not self.running_an_exposure_set:



            if self.running_an_exposure_set:
                plog("Cannot expose, camera is currently busy, waiting for exposures to clear")
                dont_wait_forever=time.time()
                while True:
                    if (time.time()-dont_wait_forever) > 5:
                        plog ("Exposure too busy for too long, returning")
                        return
                    if self.running_an_exposure_set:
                        time.sleep(0.1)
                    else:
                        break


            if req['image_type'].lower() in (
                "bias",
                "dark",
                "screen flat",
                "sky flat",
                "near flat",
                "thor flat",
                "arc flat",
                "lamp flat",
                "solar flat",
            ):
                manually_requested_calibration=True
            else:
                manually_requested_calibration=False

            self.expose_command(req, opt, user_id=command['user_id'], user_name=command['user_name'], user_roles=command['user_roles'], quick=False, manually_requested_calibration=manually_requested_calibration)

            self.active_script = None

        elif action == "darkslide_close":
            if self.darkslide_type=='COM':
                g_dev["drk"].closeDarkslide()
            elif self.darkslide_type=='ASCOM_FLI_SHUTTER':
                self.camera.Action('SetShutter', 'close')


            plog("Closing the darkslide.")
            self.darkslide_state = 'Closed'
        elif action == "darkslide_open":
            if self.darkslide_type=='COM':
                g_dev["drk"].openDarkslide()
            elif self.darkslide_type=='ASCOM_FLI_SHUTTER':
                self.camera.Action('SetShutter', 'open')



            plog("Opening the darkslide.")
            self.darkslide_state = 'Open'
        elif action == "stop":
            self.stop_command(req, opt)
            #self.running_an_exposure_set = False
            plog("STOP  STOP  STOP received.")
        else:

            plog(f"Command <{action}> not recognized.")

    ###############################
    #       Camera Commands       #
    ###############################

    """'
    Each time an expose is entered we need to look and see if the filter
    and or focus is different.  If  filter change is required, do it and look up
    the new filter offet.  Apply that as well.  Possibly this step also includes
    a temperature compensation cycle.
    Do we let focus 'float' or do we pin to a reference?  I think the latter.
    ref = actual - offset(filter): ref + offset(f) = setpoint.  At end of AF
    cycle the reference is updated logging in the filter used and the temperature.
    The old value is appended to a list which can be analysed to find the temp
    comp parameter.  It is assumed we ignore the diffuser condition when saving
    or autofocusing.  Basically use a MAD regression and expect a correlation
    value > 0.6 or so.  Store the primary temp via PWI3 and use the Wx temp
    for ambient.  We need a way to log the truss temp until we can find which
    temp best drives the compensation.
    We will assume that the default filter is a wide or lum with a nominal offset
    of 0.000  All other filter offsets are with respect to the default value.
    I.e., an autofocus of the reference filter results in the new focal position
    becoming the reference.
    The system boots up and selects the reference filter and reference focus.
    """

    def expose_command(
        self,
        required_params,
        optional_params,
        user_id='None',
        user_name='None',
        user_roles='None',
        gather_status=True,
        do_sep=True,
        no_AWS=False,
        quick=False,
        solve_it=False,
        calendar_event_id=None,
        skip_open_check=False,
        skip_daytime_check=False,
        manually_requested_calibration=False,
        useastrometrynet=False):


        self.running_an_exposure_set = True


        # First check that it isn't an exposure that doesn't need a check (e.g. bias, darks etc.)
        if not g_dev['obs'].assume_roof_open and not skip_open_check and not g_dev['obs'].scope_in_manual_mode:
        #Second check, if we are not open and available to observe, then .... don't observe!
            if g_dev['obs'].open_and_enabled_to_observe==False :
                g_dev['obs'].send_to_user("Refusing exposure request as the observatory is not enabled to observe.")
                plog("Refusing exposure request as the observatory is not enabled to observe.")
                self.running_an_exposure_set = False
                return

        # Need to pick up exposure time here
        exposure_time = float(
            required_params.get("time", 1.0)
        )

        #Third check, check it isn't daytime and institute maximum exposure time
        #Unless it is a command from the sequencer flat_scripts or a requested calibration frame
        imtype = required_params.get("image_type", "light")

        skip_daytime_check=False
        skip_calibration_check=False

        if imtype.lower() in ['pointzerozerofourfive_exposure_dark','onepointfivepercent_exposure_dark','fivepercent_exposure_dark','tenpercent_exposure_dark', 'quartersec_exposure_dark', 'halfsec_exposure_dark','threequartersec_exposure_dark','onesec_exposure_dark', 'oneandahalfsec_exposure_dark', 'twosec_exposure_dark', 'threepointfivesec_exposure_dark', 'fivesec_exposure_dark',  'sevenpointfivesec_exposure_dark','tensec_exposure_dark', 'fifteensec_exposure_dark', 'twentysec_exposure_dark', 'broadband_ss_biasdark', 'narrowband_ss_biasdark']:
            a_dark_exposure=True
        else:
            a_dark_exposure=False

        if imtype.lower() in (
            "bias",
            "dark",
            "screen flat",
            "sky flat",
            "near flat",
            "thor flat",
            "arc flat",
            "lamp flat",
            "solar flat",
        ) or a_dark_exposure:
            skip_daytime_check=True
            skip_calibration_check=True


        if not skip_daytime_check and g_dev['obs'].daytime_exposure_time_safety_on:
            sun_az, sun_alt = g_dev['evnt'].sun_az_alt_now()
            if sun_alt > -5:
                if exposure_time > float(self.config["camera"][self.name]["settings"]['max_daytime_exposure']):
                    g_dev['obs'].send_to_user("Exposure time reduced to maximum daytime exposure time: " + str(float(self.config["camera"][self.name]["settings"]['max_daytime_exposure'])))
                    plog("Exposure time reduced to maximum daytime exposure time: " + str(float(self.config["camera"][self.name]["settings"]['max_daytime_exposure'])))
                    exposure_time = float(self.config["camera"][self.name]["settings"]['max_daytime_exposure'])

        # Need to check that we are not in the middle of flats, biases or darks


        # Fifth thing, check that the sky flat latch isn't on
        # (I moved the scope during flats once, it wasn't optimal)
        if not skip_calibration_check:

            if g_dev['seq'].morn_sky_flat_latch  or g_dev['seq'].eve_sky_flat_latch: #or g_dev['seq'].sky_flat_latch:

                g_dev['obs'].send_to_user("Refusing exposure request as the observatory is currently undertaking flats.")
                plog("Refusing exposure request as the observatory is currently taking flats.")
                self.running_an_exposure_set = False
                return

        #self.running_an_exposure_set = True # This really needs to be here from the start
        # We've had multiple cases of multiple camera exposures trying to go at once
        # And it is likely because it takes a non-zero time to get to Phase II
        # So even in the setup phase the "exposure" is "busy"

        opt = optional_params
        self.hint = optional_params.get("hint", "")
        self.script = required_params.get("script", "None")

        try:

            self.zoom_factor = optional_params.get('zoom', False)
        except:
            plog("Problem with supplied Zoom factor, Camera line 1510")
            self.zoom_factor = "Full"

        if imtype.lower() in ("bias"):
            exposure_time = 0.0
            bias_dark_or_light_type_frame = 'bias'  # don't open the shutter.
            frame_type = imtype.replace(" ", "")

        elif imtype.lower() in ("dark", "lamp flat") or a_dark_exposure:

            bias_dark_or_light_type_frame = 'dark'  # don't open the shutter.
            lamps = "turn on led+tungsten lamps here, if lampflat"
            frame_type = imtype.replace(" ", "")

        elif imtype.lower() in ("near flat", "thor flat", "arc flat"):
            bias_dark_or_light_type_frame = 'light'
            lamps = "turn on ThAr or NeAr lamps here"
            frame_type = "arc"
        elif imtype.lower() in ("sky flat", "screen flat", "solar flat"):
            bias_dark_or_light_type_frame = 'light'  # open the shutter.
            lamps = "screen lamp or none"
            frame_type = imtype.replace(
                " ", ""
            )  # note banzai doesn't appear to include screen or solar flat keywords.
        elif imtype.lower() == "focus":
            frame_type = "focus"
            bias_dark_or_light_type_frame = 'light'
            lamps = None
        elif imtype.lower() == "pointing":
            frame_type = "pointing"
            bias_dark_or_light_type_frame = 'light'
            lamps = None
        else:  # 'light', 'experimental', 'autofocus probe', 'quick', 'test image', or any other image type
            bias_dark_or_light_type_frame = 'light'
            lamps = None
            if imtype.lower() in ("experimental", "autofocus probe", "auto_focus"):
                frame_type = "experimental"
                bias_dark_or_light_type_frame = 'light'
                lamps = None
            else:
                frame_type = "expose"
                bias_dark_or_light_type_frame = 'light'
                lamps = None

        self.smartstack = required_params.get('smartstack', True)
        if imtype.lower() in ["pointing", "focus"]:
            self.smartstack=False
        self.substacker = required_params.get('substack', False)


        # if self.longstack == 'no':
        #     LongStackID ='no'
        # elif not 'longstackname' in required_params:
        #     LongStackID=(datetime.datetime.now().strftime("%d%m%y%H%M%S"))
        # else:
        #     LongStackID = required_params['longstackname']

        self.pane = optional_params.get("pane", None)

        self.native_bin = self.config["camera"][self.name]["settings"]["native_bin"]
        self.ccd_sum = str(1) + ' ' + str(1)

        # readout_time = float(
        #     self.config["camera"][self.name]["settings"]["cycle_time"]
        # )
        self.estimated_readtime = (
            exposure_time + self.readout_time
        )
        count = int(
            optional_params.get("count", 1)
        )

        if count < 1:
            count = 1  # Hence frame does not repeat unless count > 1

        # Here we set up the filter, and later on possibly rotational composition.
        try:
            if g_dev["fil"].null_filterwheel == False:
                if imtype in ['bias','dark'] or a_dark_exposure:
                    requested_filter_name = 'dark'

                elif imtype in ['pointing'] and self.config["camera"][self.name]["settings"]['is_osc']:
                    requested_filter_name = 'lum'
                else:
                    requested_filter_name = str(
                        optional_params.get(
                            "filter",
                            self.config["filter_wheel"]["filter_wheel1"]["settings"][
                                "default_filter"
                            ],
                        )
                    )

                # Check if filter needs changing, if so, change.
                self.current_filter= g_dev['fil'].filter_selected
                if not self.current_filter == requested_filter_name:
                    try:
                        self.current_filter, filt_pointer, filter_offset = g_dev["fil"].set_name_command(
                            {"filter": requested_filter_name}, {}
                        )

                        # self.current_offset = g_dev[
                        #     "fil"
                        # ].filter_offset  # TEMP   NBNBNB This needs fixing

                        self.current_offset = 0

                    except:
                        plog ("Failed to change filter! Cancelling exposure.")
                        ##DEBUG Error on 20230703  System halted here. putting in
                        ##a breakpoint to catch this path next time.  WER
                        plog(traceback.format_exc())
                        #breakpoint()
                        self.running_an_exposure_set = False
                        return



                if self.current_filter == "none" or self.current_filter == None :
                    plog("skipping exposure as no adequate filter match found")
                    g_dev["obs"].send_to_user("Skipping Exposure as no adequate filter found for requested observation")
                    self.running_an_exposure_set = False
                    return

                self.current_filter = g_dev['fil'].filter_selected
            else:
                self.current_filter = self.config["filter_wheel"]["filter_wheel1"]["name"]
        except Exception as e:
            plog("Camera filter setup:  ", e)
            plog(traceback.format_exc())

        this_exposure_filter = self.current_filter
        if g_dev["fil"].null_filterwheel == False:
            exposure_filter_offset = self.current_offset
        else:
            exposure_filter_offset = 0

         # Always check rotator just before exposure  The Rot jitters wehn parked so
         # this give rot moving report during bia darks
        rot_report=0
        if g_dev['rot']!=None:
            if not g_dev['mnt'].rapid_park_indicator and not g_dev['obs'].rotator_has_been_checked_since_last_slew:
                g_dev['obs'].rotator_has_been_checked_since_last_slew = True
                while g_dev['rot'].rotator.IsMoving:
                        if rot_report == 0 and (imtype not in ['bias', 'dark'] or a_dark_exposure):
                            plog("Waiting for camera rotator to catch up. ")
                            g_dev["obs"].send_to_user("Waiting for camera rotator to catch up before exposing.")

                            rot_report=1
                        time.sleep(0.2)
                        if g_dev["obs"].stop_all_activity:
                            Nsmartstack=1
                            sskcounter=2
                            plog('stop_all_activity cancelling camera exposure')
                            self.running_an_exposure_set = False
                            return


        #expresult = {}  #  This is a default return just in case
        num_retries = 0
        incoming_exposure_time=exposure_time
        g_dev['obs'].request_scan_requests()
        if g_dev['seq'].blockend != None:
            g_dev['obs'].request_update_calendar_blocks()
        for seq in range(count):

            #pre_exposure_overhead_timer=time.time()

            # SEQ is the outer repeat loop and takes count images; those individual exposures are wrapped in a
            # retry-3-times framework with an additional timeout included in it.

            g_dev["obs"].request_update_status()





            #if seq > 0:
            #    g_dev["obs"].update_status()

            ## Vital Check : Has end of observing occured???
            ## Need to do this, SRO kept taking shots til midday without this
            if imtype.lower() in ["light"] or imtype.lower() in ["expose"]:
                if not g_dev['obs'].scope_in_manual_mode and g_dev['events']['Observing Ends'] < ephem.Date(ephem.now()+ (exposure_time *ephem.second)):
                    plog ("Sorry, exposures are outside of night time.")
                    self.running_an_exposure_set = False
                    return 'outsideofnighttime'
                if g_dev['events']['Sun Set'] > g_dev['events']['End Eve Sky Flats']:
                    if not g_dev['obs'].scope_in_manual_mode and not (g_dev['events']['Sun Set'] < ephem.Date(ephem.now()+ (exposure_time *ephem.second))):
                        plog ("Sorry, exposures are outside of night time.")
                        self.running_an_exposure_set = False
                        return 'outsideofnighttime'
                if g_dev['events']['Sun Set'] < g_dev['events']['End Eve Sky Flats']:
                    if not g_dev['obs'].scope_in_manual_mode and not (g_dev['events']['End Eve Sky Flats'] < ephem.Date(ephem.now()+ (exposure_time *ephem.second))):
                        plog ("Sorry, exposures are outside of night time.")
                        self.running_an_exposure_set = False
                        return 'outsideofnighttime'

            self.pre_mnt = []
            self.pre_rot = []
            self.pre_foc = []
            self.pre_ocn = []

            # Within each count - which is a single requested exposure, IF it is a smartstack
            # Then we divide each count up into individual smartstack exposures.
            ssBaseExp=self.config["camera"][self.name]["settings"]['smart_stack_exposure_time']
            ssExp=self.config["camera"][self.name]["settings"]['smart_stack_exposure_time']
            ssNBmult=self.config["camera"][self.name]["settings"]['smart_stack_exposure_NB_multiplier']
            dark_exp_time = self.config['camera']['camera_1_1']['settings']['dark_exposure']



            if g_dev["fil"].null_filterwheel == False:
                if self.current_filter.lower() in ['ha', 'o3', 's2', 'n2', 'y', 'up', 'u']:
                    ssExp = ssExp * ssNBmult # For narrowband and low throughput filters, increase base exposure time.
                #
            if not imtype.lower() in ["light", "expose"]:
                Nsmartstack=1
                SmartStackID='no'
                smartstackinfo='no'
                exposure_time=incoming_exposure_time

            elif (self.smartstack == 'yes' or self.smartstack == True) and (incoming_exposure_time > ssExp):
                Nsmartstack=np.ceil(incoming_exposure_time / ssExp)
                exposure_time=ssExp
                SmartStackID=(datetime.datetime.now().strftime("%d%m%y%H%M%S"))
                if self.current_filter.lower() in ['ha', 'o3', 's2', 'n2', 'y', 'up', 'u'] :
                    smartstackinfo='narrowband'
                else:
                    smartstackinfo='broadband'


            else:
                Nsmartstack=1
                SmartStackID='no'
                smartstackinfo='no'
                exposure_time=incoming_exposure_time

            # Create a unique yet arbitrary code for the token

            real_time_token=g_dev['name'] + '_' + self.alias + '_' + g_dev["day"] + '_' + self.current_filter.lower() + '_' + smartstackinfo + '_' + str(ssBaseExp) + "_" + str( ssBaseExp * ssNBmult) + '_' + str(dark_exp_time) + '_' + str(datetime.datetime.now()).replace(' ','').replace('-','').replace(':','').replace('.','')
            real_time_files=[]



            self.retry_camera = 1
            self.retry_camera_start_time = time.time()

            if Nsmartstack > 1 :
                self.currently_in_smartstack_loop=True
                self.initial_smartstack_ra= g_dev['mnt'].return_right_ascension()
                self.initial_smartstack_dec= g_dev['mnt'].return_declination()
            else:
                self.initial_smartstack_ra= None
                self.initial_smartstack_dec= None
                self.currently_in_smartstack_loop=False

            #Repeat camera acquisition loop to collect all smartstacks necessary
            #The variable Nsmartstacks defaults to 1 - e.g. normal functioning
            #When a smartstack is not requested.
            for sskcounter in range(int(Nsmartstack)):


                # If the pier just flipped, trigger a recentering exposure.
                #if not g_dev['mnt'].rapid_park_indicator:# and not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
                if not g_dev['obs'].mountless_operation:

                    if not g_dev['mnt'].rapid_park_indicator:# and (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
                        #if not (g_dev['mnt'].previous_pier_side==g_dev['mnt'].rapid_pier_indicator) :
                        self.wait_for_slew()
                        if g_dev['mnt'].pier_flip_detected==True:
                            plog ("PIERFLIP DETECTED, RECENTERING.")
                            g_dev["obs"].send_to_user("Pier Flip detected, recentering.")
                            g_dev['obs'].pointing_recentering_requested_by_platesolve_thread = True
                            g_dev['obs'].pointing_correction_request_time = time.time()
                            g_dev['obs'].pointing_correction_request_ra = g_dev["mnt"].last_ra_requested
                            g_dev['obs'].pointing_correction_request_dec = g_dev["mnt"].last_dec_requested
                            g_dev['obs'].pointing_correction_request_ra_err = 0
                            g_dev['obs'].pointing_correction_request_dec_err = 0
                            g_dev['obs'].check_platesolve_and_nudge(no_confirmation=False)
                            Nsmartstack=1
                            sskcounter=2
                            self.currently_in_smartstack_loop=False
                            break
                        else:
                            #plog ("MTF temp reporting. No pierflip.")
                            pass
                    #g_dev['mnt'].previous_pier_side=g_dev['mnt'].rapid_pier_indicator

                    if g_dev['obs'].pointing_recentering_requested_by_platesolve_thread:
                        plog ("Major shift detected, recentering.")
                        g_dev['obs'].check_platesolve_and_nudge()

                self.tempStartupExposureTime=time.time()

                if Nsmartstack > 1 :
                    plog ("Smartstack " + str(sskcounter+1) + " out of " + str(Nsmartstack))
                    g_dev["obs"].request_update_status()



                self.retry_camera = 1
                self.retry_camera_start_time = time.time()
                while self.retry_camera > 0:
                    if g_dev["obs"].stop_all_activity:
                        Nsmartstack=1
                        sskcounter=2
                        # if expresult != None and expresult != {}:
                        #     if expresult["stopped"] is True:
                        g_dev["obs"].stop_all_activity = False
                        plog("Camera retry loop stopped by Cancel Exposure")
                        self.running_an_exposure_set = False
                        #plog ("stop_all_activity cancelling out of camera exposure")
                        self.currently_in_smartstack_loop=False
                        self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                        return

                    # Check that the block isn't ending during normal observing time (don't check while biasing, flats etc.)
                    if g_dev['seq'].blockend != None: # Only do this check if a block end was provided.

                    # Check that the exposure doesn't go over the end of a block
                        endOfExposure = datetime.datetime.utcnow() + datetime.timedelta(seconds=exposure_time)
                        now_date_timeZ = endOfExposure.isoformat().split('.')[0] +'Z'

                        #plog (now_date_timeZ)
                        #plog (g_dev['seq'].blockend)

                        blockended = now_date_timeZ  >= g_dev['seq'].blockend

                        #plog (blockended)

                        if blockended or ephem.Date(ephem.now()+ (exposure_time *ephem.second)) >= \
                            g_dev['events']['End Morn Bias Dark']:
                            plog ("Exposure overlays the end of a block or the end of observing. Skipping Exposure.")
                            plog ("And Cancelling SmartStacks.")
                            Nsmartstack=1
                            sskcounter=2
                            self.running_an_exposure_set = False
                            self.currently_in_smartstack_loop=False
                            self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                            return 'blockend'

                    # Check that the calendar event that is running the exposure
                    # Hasn't completed already
                    # Check whether calendar entry is still existant.
                    # If not, stop running block
                    if not calendar_event_id == None:
                        #print ("ccccccc")



                        foundcalendar=False

                        for tempblock in g_dev['seq'].blocks:
                            try:
                                if tempblock['event_id'] == calendar_event_id :
                                    foundcalendar=True
                                    g_dev['seq'].blockend=tempblock['end']

                                    #breakpoint()
                            except:
                                plog("glitch in calendar finder")
                                plog(str(tempblock))
                        now_date_timeZ = datetime.datetime.utcnow().isoformat().split('.')[0] +'Z'
                        if foundcalendar == False or now_date_timeZ >= g_dev['seq'].blockend:
                            plog ("could not find calendar entry, cancelling out of block.")
                            plog ("And Cancelling SmartStacks.")
                            Nsmartstack=1
                            sskcounter=2
                            self.currently_in_smartstack_loop=False
                            self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                            self.running_an_exposure_set = False
                            return 'calendarend'

                    # # Check that the roof hasn't shut
                    # g_dev['obs'].get_enclosure_status_from_aws()

                    if not g_dev['obs'].assume_roof_open and not g_dev['obs'].scope_in_manual_mode and 'Closed' in g_dev['obs'].enc_status['shutter_status'] and imtype not in ['bias', 'dark'] and not a_dark_exposure:

                        plog("Roof shut, exposures cancelled.")
                        g_dev["obs"].send_to_user("Roof shut, exposures cancelled.")

                        self.open_and_enabled_to_observe = False
                        if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                            g_dev['obs'].cancel_all_activity()  #NB Kills bias dark
                        if not g_dev['mnt'].rapid_park_indicator:
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()
                        plog ("And Cancelling SmartStacks.")
                        Nsmartstack=1
                        sskcounter=2
                        self.currently_in_smartstack_loop=False
                        self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                        self.running_an_exposure_set = False
                        return 'roofshut'


                    try:
                        #self.running_an_exposure_set = True

                        if self.maxim or self.ascom or self.theskyx or self.qhydirect:

                            ldr_handle_time = None
                            ldr_handle_high_time = None  #  This is not maxim-specific

                            if self.has_darkslide and bias_dark_or_light_type_frame == 'light':
                                if self.darkslide_state != 'Open':
                                    if self.darkslide_type=='COM':
                                        if not self.darkslide_instance.openDarkslide():
                                            self.currently_in_smartstack_loop=False
                                            self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                                            self.running_an_exposure_set = False
                                            plog ("Darkslide Failed. Cancelling exposure")
                                            return 'darkslidefail'
                                    elif self.darkslide_type=='ASCOM_FLI_SHUTTER':
                                        self.camera.Action('SetShutter', 'open')
                                    self.darkslide_open = True
                                    self.darkslide_state = 'Open'
                            elif self.has_darkslide and (bias_dark_or_light_type_frame == 'bias' or bias_dark_or_light_type_frame == 'dark'):
                                if self.darkslide_state != 'Closed':
                                    if self.darkslide_type=='COM':
                                        if not self.darkslide_instance.closeDarkslide():
                                            self.currently_in_smartstack_loop=False
                                            self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                                            self.running_an_exposure_set = False
                                            plog ("Darkslide Failed. Cancelling exposure")
                                            return 'darkslidefail'
                                        # self.darkslide_instance.closeDarkslide()
                                    elif self.darkslide_type=='ASCOM_FLI_SHUTTER':
                                        self.camera.Action('SetShutter', 'close')

                                    self.darkslide_open = False
                                    self.darkslide_state = 'Closed'




                            # Good spot to check if we need to nudge the telescope

                            g_dev['obs'].check_platesolve_and_nudge()
                            g_dev['obs'].time_of_last_exposure = time.time()

                            # During a pre-exposure, we don't want the update to be
                            # syncronous!
                            #g_dev["obs"].request_full_update()
                            #g_dev['obs'].update()




                            observer_user_name = user_name

                            try:
                                self.user_id = user_id
                                if self.user_id != self.last_user_id:
                                    self.last_user_id = self.user_id
                                observer_user_id= self.user_id
                            except:
                                observer_user_id= 'Tobor'
                                plog("Failed user_id")



                            self.current_exposure_time=exposure_time



                            # Always check rotator just before exposure  The Rot jitters wehn parked so

                            if not g_dev['obs'].mountless_operation:
                                rot_report=0
                                if g_dev['rot']!=None:
                                    if not g_dev['mnt'].rapid_park_indicator and not g_dev['obs'].rotator_has_been_checked_since_last_slew:
                                        g_dev['obs'].rotator_has_been_checked_since_last_slew = True
                                        while g_dev['rot'].rotator.IsMoving:    #This signal fibrulates!
                                            #if g_dev['rot'].rotator.IsMoving:
                                             if rot_report == 0 :
                                                 plog("Waiting for camera rotator to catch up. ")
                                                 g_dev["obs"].send_to_user("Waiting for instrument rotator to catch up before exposing.")

                                                 rot_report=1
                                             time.sleep(0.2)
                                             if g_dev["obs"].stop_all_activity:
                                                 Nsmartstack=1
                                                 sskcounter=2
                                                 plog ("stop_all_activity cancelling out of camera exposure")
                                                 self.currently_in_smartstack_loop=False
                                                 self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                                                 self.running_an_exposure_set = False
                                                 return


                            if (bias_dark_or_light_type_frame in ["bias", "dark"] or 'flat' in frame_type or a_dark_exposure) and not manually_requested_calibration:

                                # Check that the temperature is ok before accepting
                                current_camera_temperature, cur_humidity, cur_pressure = (g_dev['cam']._temperature())
                                current_camera_temperature = float(current_camera_temperature)
                                if abs(float(current_camera_temperature) - float(g_dev['cam'].setpoint)) > self.temp_tolerance:
                                    plog ("temperature out of +/- range for calibrations ("+ str(current_camera_temperature)+"), NOT attempting calibration frame")
                                    g_dev['obs'].camera_sufficiently_cooled_for_calibrations = False
                                    expresult = {}
                                    expresult["error"] = True
                                    expresult["patch"] = None
                                    self.running_an_exposure_set = False
                                    self.currently_in_smartstack_loop=False
                                    self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                                    return expresult

                                else:
                                    #plog ("temperature in range for calibrations ("+ str(current_camera_temperature)+"), attempting calibration frame")
                                    g_dev['obs'].camera_sufficiently_cooled_for_calibrations = True


                            #plog ("pre-exposure overhead: " + str(time.time() -pre_exposure_overhead_timer) +"s.")
                            self.wait_for_slew()


                            # Check there hasn't been a cancel sent through
                            if g_dev["obs"].stop_all_activity:
                                plog ("stop_all_activity cancelling out of camera exposure")
                                Nsmartstack=1
                                sskcounter=2
                                self.currently_in_smartstack_loop=False
                                self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                                self.running_an_exposure_set = False
                                return 'cancelled'

                            #plog ("Time between end of last exposure and start of next minus exposure time: " + str(time.time() -  self.end_of_last_exposure_time - exposure_time))

                            if not g_dev['obs'].mountless_operation and not g_dev['mnt'].rapid_park_indicator:
                                self.wait_for_slew()
                                if g_dev['mnt'].pier_flip_detected==True:
                                    plog("Detected a pier flip just before exposure!")
                                    g_dev["obs"].send_to_user("Pier Flip detected, recentering.")
                                    g_dev['obs'].pointing_recentering_requested_by_platesolve_thread = True
                                    g_dev['obs'].pointing_correction_request_time = time.time()
                                    g_dev['obs'].pointing_correction_request_ra = g_dev["mnt"].last_ra_requested
                                    g_dev['obs'].pointing_correction_request_dec = g_dev["mnt"].last_dec_requested
                                    g_dev['obs'].pointing_correction_request_ra_err = 0
                                    g_dev['obs'].pointing_correction_request_dec_err = 0
                                    g_dev['obs'].check_platesolve_and_nudge(no_confirmation=False)
                                    Nsmartstack=1
                                    sskcounter=2
                                    self.currently_in_smartstack_loop=False
                                    break

                            if imtype in ['bias','dark'] or a_dark_exposure:
                                # Artifical wait time for bias and dark
                                # calibrations to allow pixels to cool
                                time.sleep(1)

                            if not imtype in ['bias','dark'] and not a_dark_exposure and not frame_type[-4:] == "flat" and not g_dev['obs'].scope_in_manual_mode:

                                if g_dev['events']['Morn Sky Flats'] < g_dev['events']['Sun Rise']:
                                    last_time = g_dev['events']['Morn Sky Flats']
                                else:
                                    last_time = g_dev['events']['Sun Rise']

                                if last_time < ephem.Date(ephem.now()):
                                    plog("Observing has ended for the evening, cancelling out of exposures.")
                                    g_dev["obs"].send_to_user("Observing has ended for the evening, cancelling out of exposures.")
                                    Nsmartstack=1
                                    sskcounter=2
                                    self.currently_in_smartstack_loop=False
                                    break



                            # Sort out if it is a substack
                            # If request actually requested a substack
                            if self.substacker:
                                self.substacker=False
                                broadband_ss_biasdark_exp_time = self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_time']
                                narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_NB_multiplier']
                                if self.config['camera']['camera_1_1']['settings']['substack']:
                                    if not imtype in ['bias','dark'] and not a_dark_exposure and not frame_type[-4:] == "flat" and not frame_type=='pointing':
                                        if exposure_time % 10 == 0 and exposure_time >= 30 and exposure_time < 1.25 * narrowband_ss_biasdark_exp_time:
                                            self.substacker=True

                            # If it is meant to be a substacker image
                            # Make sure there is actually a bias, dark, flat and bpm
                            # otherwise a substack is pointless.
                            if self.substacker:
                                self.substacker=False
                                # Must have a biasdark
                                if 'tensec_exposure_biasdark' in self.darkFiles:
                                    if this_exposure_filter.lower() + '_bin1' in self.flatFiles:
                                        if '1' in self.bpmFiles:
                                            self.substacker=True
                                        else:
                                            plog ("Could not engage substacking as the bad pixel mask is missing")
                                    else:
                                        plog ("Could not engage substacking as the filter requested has no flat")
                                else:
                                    plog ("Could not engage substacking as the appropriate biasdark")

                            plog ("SUBSTACK: " +str(self.substacker))
                            #breakpoint()

                            # Adjust pointing exposure time relative to known focus
                            if not g_dev['seq'].focussing and frame_type=='pointing':
                                try:
                                    last_fwhm=g_dev['obs'].fwhmresult["FWHM"]

                                    if last_fwhm > 4.0:
                                        exposure_time=exposure_time * 4
                                    elif last_fwhm > 3:
                                        exposure_time=exposure_time * 3
                                    elif last_fwhm > 2.5:
                                        exposure_time=exposure_time * 2
                                    elif last_fwhm > 2.0:
                                        exposure_time=exposure_time * 1.5
                                except:
                                    plog ("can't adjust exposure time for pointing if no previous focus known")

                                #breakpoint()

                            if g_dev["fil"].null_filterwheel == False:
                                while g_dev['fil'].filter_changing:
                                    #plog ("Waiting for filter_change")
                                    time.sleep(0.05)

                            g_dev['foc'].adjust_focus()

                            reporty=0
                            while g_dev['foc'].focuser_is_moving:
                                if reporty==0:
                                    #plog ("Waiting for focuser to finish moving")
                                    reporty=1
                                time.sleep(0.05)

                            # For some focusers, there is a non-trivial vibration time to
                            # wait until the mirror settles down before exposure
                            # that isn't even caught in the focuser threads.
                            # So if it has moved, as indicated by reporty
                            # Then there is a further check before moving on
                            if reporty==1:
                                tempfocposition=g_dev['foc'].get_position_actual()
                                while True:
                                    time.sleep(0.2)
                                    nowfocposition=g_dev['foc'].get_position_actual()
                                    if tempfocposition==nowfocposition:
                                        break
                                    else:
                                        plog("Detecting focuser still changing.")
                                        tempfocposition=copy.deepcopy(nowfocposition)





                            #self.running_an_exposure_set = True

                            start_time_of_observation=time.time()
                            self.start_time_of_observation=time.time()
                            self.shutter_open = True
                            self._expose(exposure_time, bias_dark_or_light_type_frame)
                            self.end_of_last_exposure_time=time.time()

                            # After sending the exposure command, the camera is exposing
                            # So commands placed here are essentially "cost-free" in terms of overhead.
                            # As long as they don't take longer than the actual exposure time

                            # Make sure the latest mount_coordinates are updated. HYPER-IMPORTANT!
                            # But not so important if you aren't platesovling - e.g. short exposures
                            # where time is of the essence and we aren't platesolving anyway
                            googtime=time.time()
                            if not g_dev['obs'].mountless_operation:
                                if exposure_time >= 1:
                                    ra_at_time_of_exposure , dec_at_time_of_exposure = g_dev["mnt"].get_mount_coordinates_after_next_update()
                                else:
                                    ra_at_time_of_exposure = g_dev["mnt"].current_icrs_ra
                                    dec_at_time_of_exposure = g_dev["mnt"].current_icrs_dec
                            else:
                                ra_at_time_of_exposure = 99.9
                                dec_at_time_of_exposure = 99.9
                            #print ("Mount RA and Dec readtime " +str(time.time()-googtime))

                            if not g_dev['obs'].mountless_operation:
                                airmass = round(g_dev['mnt'].airmass, 4)

                                airmass_of_observation = airmass
                                g_dev["airmass"] = float(airmass_of_observation)

                                azimuth_of_observation = g_dev['mnt'].az
                                altitude_of_observation = g_dev['mnt'].alt
                            else:
                                airmass_of_observation = 99.9

                                azimuth_of_observation = 99.9
                                altitude_of_observation = 99.9



                        else:
                            plog("Something terribly wrong, driver not recognized.!")
                            expresult = {}
                            expresult["error"] = True
                            self.running_an_exposure_set = False
                            self.shutter_open=False
                            self.currently_in_smartstack_loop=False
                            self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                            return expresult

                        self.pre_mnt = []
                        self.pre_rot = []
                        self.pre_foc = []
                        self.pre_ocn = []
                        try:
                            g_dev["foc"].get_quick_status(self.pre_foc)
                            try:
                                g_dev["rot"].get_quick_status(self.pre_rot)
                            except:
                                pass
                        except:
                            plog ("couldn't grab quick status focus")

                        if not g_dev['obs'].mountless_operation:
                            g_dev["mnt"].get_rapid_exposure_status(
                                self.pre_mnt
                            )  # Should do this close to the exposure


                        # We call below to keep this subroutine a reasonable length, Basically still in Phase 2
                        #breakpoint()
                        expresult = self.finish_exposure(
                            exposure_time,
                            frame_type,
                            count - seq,
                            gather_status,
                            do_sep,
                            no_AWS,
                            None,
                            None,
                            quick=quick,
                            low=ldr_handle_time,
                            high=ldr_handle_high_time,
                            script=self.script,
                            opt=opt,
                            solve_it=solve_it,
                            smartstackid=SmartStackID,
                            #longstackid=LongStackID,
                            sskcounter=sskcounter,
                            Nsmartstack=Nsmartstack,
                            this_exposure_filter=this_exposure_filter,
                            start_time_of_observation=start_time_of_observation,
                            exposure_filter_offset=exposure_filter_offset,
                            ra_at_time_of_exposure=ra_at_time_of_exposure,
                            dec_at_time_of_exposure=dec_at_time_of_exposure,
                            observer_user_name=observer_user_name,
                            observer_user_id=observer_user_id,
                            airmass_of_observation=airmass_of_observation,
                            azimuth_of_observation = azimuth_of_observation,
                            altitude_of_observation = altitude_of_observation,
                            manually_requested_calibration=manually_requested_calibration,
                            # initial_smartstack_ra=initial_smartstack_ra,
                            # initial_smartstack_dec= initial_smartstack_dec,
                            zoom_factor=self.zoom_factor,
                            useastrometrynet=useastrometrynet,
                            a_dark_exposure=a_dark_exposure,
                            substack=self.substacker
                        )  # NB all these parameters are crazy!



                        #self.running_an_exposure_set = False
                        self.retry_camera = 0
                        #self.currently_in_smartstack_loop=False
                        #print ("EXPRESULT: " + str(expresult))
                        if not frame_type[-4:] == "flat" and not frame_type.lower() in ["bias", "dark"] and not a_dark_exposure and not frame_type.lower()=='focus' and not frame_type=='pointing':
                            try:
                                real_time_files.append(str(expresult["real_time_filename"]))
                                #print ("REAL TIME FILES LIST: " + str(real_time_files))
                            except:
                                #print (frame_type)
                                print ("Did not include real time filename due to exposure cancelling (probably)")
                                #plog(traceback.format_exc())
                        break
                    except Exception as e:
                        plog("Exception in camera retry loop:  ", e)
                        plog(traceback.format_exc())
                        self.retry_camera -= 1
                        num_retries += 1
                        self.shutter_open=False
                        #self.running_an_exposure_set = False
                        #self.currently_in_smartstack_loop=False
                        continue
            #self.shutter_open=False
            #self.running_an_exposure_set = False
            self.currently_in_smartstack_loop=False


        # If the pier just flipped, trigger a recentering exposure.
        # This is here because a single exposure may have a flip in it, hence
        # we check here.
        #if not g_dev['mnt'].rapid_park_indicator:# and not (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
        if not g_dev['obs'].mountless_operation:

            if not g_dev['mnt'].rapid_park_indicator: # and (g_dev['events']['Civil Dusk'] < ephem.now() < g_dev['events']['Civil Dawn']):
                self.wait_for_slew()
                #if not (g_dev['mnt'].previous_pier_side==g_dev['mnt'].rapid_pier_indicator) :
                if g_dev['mnt'].pier_flip_detected==True:
                    plog ("PIERFLIP DETECTED, RECENTERING.")
                    g_dev["obs"].send_to_user("Pier Flip detected, recentering.")
                    g_dev['obs'].pointing_recentering_requested_by_platesolve_thread = True
                    g_dev['obs'].pointing_correction_request_time = time.time()
                    g_dev['obs'].pointing_correction_request_ra = g_dev["mnt"].last_ra_requested
                    g_dev['obs'].pointing_correction_request_dec = g_dev["mnt"].last_dec_requested
                    g_dev['obs'].pointing_correction_request_ra_err = 0
                    g_dev['obs'].pointing_correction_request_dec_err = 0
                    g_dev['obs'].check_platesolve_and_nudge(no_confirmation=False)

                else:
                    #plog ("MTF temp reporting. No pierflip.")
                    pass

        self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)

        #  This is the loop point for the seq count loop
        #self.running_an_exposure_set = False
        self.currently_in_smartstack_loop=False
        #breakpoint()

        # trap missing expresult (e.g. cancelled exposures etc.)
        if not 'expresult' in locals():
            expresult = 'error'
        self.running_an_exposure_set = False
        self.shutter_open=False
        return expresult

    def write_out_realtimefiles_token_to_disk(self,token_name,real_time_files):

        if self.config['save_raws_to_pipe_folder_for_nightly_processing']:
            if len(real_time_files) > 0:
                #print ("WRITING OUT TOKEN TO LOCAL PIPE FOLDER")
                #print (token_name)
                #print (real_time_files)
                #pipefolder = self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(g_dev["day"]) +'/'+ str(self.alias)



                # if not os.path.exists(self.config['temporary_local_pipe_archive_to_hold_files_while_copying']+'/'+ str(g_dev["day"])):
                #     os.makedirs(self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(g_dev["day"]))

                # if not os.path.exists(self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(g_dev["day"]) +'/'+ str(self.alias)):
                #     os.makedirs(self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(g_dev["day"]) +'/'+ str(self.alias))


                pipetokenfolder = self.config['pipe_archive_folder_path'] +'/tokens'
                if not os.path.exists(self.config['pipe_archive_folder_path'] +'/tokens'):
                    os.makedirs(self.config['pipe_archive_folder_path'] +'/tokens')



                with open(pipetokenfolder + "/" + token_name, 'w') as f:
                    # indent=2 is not needed but makes the file human-readable
                    # if the data is nested
                    json.dump(real_time_files, f, indent=2)




    def stop_command(self, required_params, optional_params):
        """Stop the current exposure and return the camera to Idle state."""
        self._stop_expose()
        g_dev['cam'].expresult = {}
        g_dev['cam'].expresult["stopped"] = True
        self.running_an_exposure_set = False
        self.shutter_open=False
        self.exposure_halted = True

    def finish_exposure(
        self,
        exposure_time,
        frame_type,
        counter,
        seq,
        gather_status=True,
        do_sep=False,
        no_AWS=False,
        start_x=None,
        start_y=None,
        quick=False,
        low=0,
        high=0,
        script="False",
        opt=None,
        solve_it=False,
        smartstackid='no',
        #longstackid='no',
        sskcounter=0,
        Nsmartstack=1,
        this_exposure_filter=None,
        start_time_of_observation=None,
        exposure_filter_offset=None,
        ra_at_time_of_exposure=None,
        dec_at_time_of_exposure=None,
        observer_user_name=None,
        observer_user_id=None,
        airmass_of_observation=None,
        azimuth_of_observation=None,
        altitude_of_observation=None,
        manually_requested_calibration=False,
        # initial_smartstack_ra=None,
        # initial_smartstack_dec=None,
        zoom_factor=False,
        useastrometrynet=False,
        a_dark_exposure=False,
        substack=False

    ):

        #breakpoint()
        #self.expresult={}
        plog(
            "Exposure Started:  " + str(exposure_time) + "s ",
            frame_type
        )
        #plog("Finish Exposure, zoom:  ", zoom_factor)

        try:
            if opt["object_name"] == '':
                opt["object_name"] = 'Unknown'
        except:
            opt["object_name"] = 'Unknown'


        try:
            opt["object_name"]
        except:
            opt["object_name"] = 'Unknown'

        try:
            filter_ui_info=opt['filter']
        except:
            filter_ui_info='filterless'

        if frame_type in (
            "flat",
            "screenflat",
            "skyflat",
            "dark",
            "bias") or a_dark_exposure:
            g_dev["obs"].send_to_user(
                "Starting "
                + str(exposure_time)
                + "s "
                + str(frame_type)
                + " calibration exposure.",
                p_level="INFO",
            )
        elif frame_type in ("focus", "auto_focus"):
            g_dev["obs"].send_to_user(
                "Starting "
                + str(exposure_time)
                + "s "
                + str(frame_type)
                + "  exposure.",
                p_level="INFO",
            )
        elif frame_type in ("pointing"):
            g_dev["obs"].send_to_user(
                "Starting "
                + str(exposure_time)
                + "s "
                + str(frame_type)
                + "  exposure.",
                p_level="INFO",
            )

        elif Nsmartstack > 1 and self.current_filter.lower() in ['ha', 'hac', 'o3', 's2', 'n2', 'hb', 'hbc', 'hd', 'hga', 'cr']:  #, 'y', 'up', 'u']:
            plog ("Starting narrowband " +str(exposure_time) + "s smartstack " + str(sskcounter+1) + " out of " + str(int(Nsmartstack)) + " of "
            + str(opt["object_name"])
            + " by user: " + str(observer_user_name))
            g_dev["obs"].send_to_user ("Starting narrowband " +str(exposure_time) + "s smartstack " + str(sskcounter+1) + " out of " + str(int(Nsmartstack)) + " by user: " + str(observer_user_name))
        elif Nsmartstack > 1 :
            plog ("Starting broadband " +str(exposure_time) + "s smartstack " + str(sskcounter+1) + " out of " + str(int(Nsmartstack)) + " of "
            + str(opt["object_name"])
            + " by user: " + str(observer_user_name))
            g_dev["obs"].send_to_user ("Starting broadband " +str(exposure_time) + "s smartstack " + str(sskcounter+1) + " out of " + str(int(Nsmartstack)) + " by user: " + str(observer_user_name))
        else:
            if "object_name" in opt:
                g_dev["obs"].send_to_user(
                    "Starting "
                    + str(exposure_time)
                    + "s " + str(filter_ui_info) + " exposure of "
                    + str(opt["object_name"])
                    + " by user: "
                    + str(observer_user_name) + '. ' + str(int(opt['count']) - int(counter) + 1) + " of " + str(opt['count']),
                    p_level="INFO",
                )

        count=int(opt['count'])

        self.status_time = time.time() + 10
        self.post_mnt = []
        self.post_rot = []
        self.post_foc = []
        self.post_ocn = []
        counter = 0

        # cycle_time = (
        #     float(self.config["camera"][self.name]["settings"]['cycle_time'])
        # )

        if substack:
            # It takes time to do the median stack... add in a bit of an empirical overhead
            # We also have to factor in all the readout times unlike a single exposure
            # As the readouts are all done in the substack thread.
            stacking_overhead= 0.0005*pow(exposure_time,2) + 0.0334*exposure_time
            #plog ("Expected stacking overhead: " + str(stacking_overhead))
            cycle_time=exposure_time + ((exposure_time / 10))*self.readout_time + stacking_overhead
            self.completion_time = start_time_of_observation + cycle_time
            #breakpoint()
        # For file-based readouts, we need to factor in the readout time
        # and wait for that as well as the exposure time.
        # Currently this is just theskyx... probably also ascom and maxim but we don't use either of them anymore
        elif self.theskyx:
            cycle_time=(0.75*self.readout_time)+exposure_time # We have a 25% buffer so that it can record faster readout times.
            self.completion_time = start_time_of_observation + cycle_time
        # Otherwise just wait for the exposure_time to end
        # Because the readout time occurs in the image aquisition function
        else:
            cycle_time=exposure_time
            self.completion_time = start_time_of_observation + cycle_time

        expresult = {"error": False}
        quartileExposureReport = 0
        self.plog_exposure_time_counter_timer=time.time() -3.0

        exposure_scan_request_timer=time.time() - 8
        g_dev["obs"].exposure_halted_indicator =False



        # This command takes 0.1s to do, so happens just during the start of exposures
        g_dev['cam'].tempccdtemp, g_dev['cam'].ccd_humidity, g_dev['cam'].ccd_pressure = (g_dev['cam']._temperature())

        block_and_focus_check_done=False

        if exposure_time <= 5.0:
            g_dev['obs'].request_scan_requests()
            if g_dev['seq'].blockend != None:
                g_dev['obs'].request_update_calendar_blocks()
            try:
                focus_position=g_dev['foc'].current_focus_position
            except:
                pass
            block_and_focus_check_done=True

        pointingfocus_masterdark_done=False
        check_nudge_after_shutter_closed=False


        if frame_type[-5:] in ["focus", "probe", "ental"]:
            focus_image = True
        else:
            focus_image = False

        broadband_ss_biasdark_exp_time = self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_time']
        narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * self.config['camera']['camera_1_1']['settings']['smart_stack_exposure_NB_multiplier']
        dark_exp_time = self.config['camera']['camera_1_1']['settings']['dark_exposure']




        while True:

            if (
                time.time() < self.completion_time or self.async_exposure_lock==True
            ):

                # Scan requests every 4 seconds... primarily hunting for a "Cancel/Stop"
                if time.time() - exposure_scan_request_timer > 4:# and (time.time() - self.completion_time) > 4:
                    exposure_scan_request_timer=time.time()

                    g_dev['obs'].request_scan_requests()
                    #g_dev['obs'].scan_requests()


                    # Check there hasn't been a cancel sent through
                    if g_dev["obs"].stop_all_activity:
                        plog ("stop_all_activity cancelling out of camera exposure")
                        Nsmartstack=1
                        sskcounter=2
                        expresult["error"] = True
                        expresult["stopped"] = True
                        g_dev["obs"].exposure_halted_indicator =False
                        self.currently_in_smartstack_loop=False
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        return expresult

                    if g_dev["obs"].exposure_halted_indicator:
                        expresult["error"] = True
                        expresult["stopped"] = True
                        g_dev["obs"].exposure_halted_indicator =False
                        plog ("Exposure Halted Indicator On. Cancelling Exposure.")
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        return expresult

                remaining = round(self.completion_time - time.time(), 1)


                # FOR POINTING AND FOCUS EXPOSURES, CONSTRUCT THE SCALED MASTERDARK WHILE
                # THE EXPOSURE IS RUNNING
                if (frame_type=='pointing' or focus_image == True) and not pointingfocus_masterdark_done and smartstackid == 'no':
                    #plog ("constructing scaled masterdark during exposure")
                    if not self.substacker:
                        try:
                            # Sort out an intermediate dark
                            fraction_through_range=0
                            if exposure_time < 0.5:
                                intermediate_tempdark=(g_dev['cam'].darkFiles['halfsec_exposure_dark']*exposure_time)
                            elif exposure_time < 2.0:
                                fraction_through_range=(exposure_time-0.5)/(2.0-0.5)
                                intermediate_tempdark=(fraction_through_range * g_dev['cam'].darkFiles['twosec_exposure_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['halfsec_exposure_dark'])

                            elif exposure_time < 10.0:
                                fraction_through_range=(exposure_time-2)/(10.0-2.0)
                                intermediate_tempdark=(fraction_through_range * g_dev['cam'].darkFiles['tensec_exposure_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['twosec_exposure_dark'])

                            elif exposure_time < broadband_ss_biasdark_exp_time:
                                fraction_through_range=(exposure_time-10)/(broadband_ss_biasdark_exp_time-10.0)
                                intermediate_tempdark=(fraction_through_range * g_dev['cam'].darkFiles['broadband_ss_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['tensec_exposure_dark'])

                            elif exposure_time < narrowband_ss_biasdark_exp_time:
                                fraction_through_range=(exposure_time-broadband_ss_biasdark_exp_time)/(narrowband_ss_biasdark_exp_time-broadband_ss_biasdark_exp_time)
                                intermediate_tempdark=(fraction_through_range * g_dev['cam'].darkFiles['narrowband_ss_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['broadband_ss_dark'])

                            elif dark_exp_time > narrowband_ss_biasdark_exp_time:
                                fraction_through_range=(exposure_time-narrowband_ss_biasdark_exp_time)/(dark_exp_time -narrowband_ss_biasdark_exp_time)
                                intermediate_tempdark=(fraction_through_range * g_dev['cam'].darkFiles[str(1)]) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['narrowband_ss_dark'])
                            else:
                                intermediate_tempdark=(g_dev['cam'].darkFiles['narrowband_ss_dark'])
                        except:
                            try:
                                intermediate_tempdark=(g_dev['cam'].darkFiles['1'])
                            except:
                                pass
                        pointingfocus_masterdark_done=True

                    #plog ("grabbing masterflat during exposure")
                    intermediate_tempflat=np.load(g_dev['cam'].flatFiles[str(g_dev['cam'].current_filter + "_bin" + str(1))])

                if remaining > 0:
                    if time.time() - self.plog_exposure_time_counter_timer > 10.0:
                        self.plog_exposure_time_counter_timer=time.time()
                        plog(
                            '||  ' + str(round(remaining, 1)) + "sec.",
                            str(round(100 * remaining / cycle_time, 1)) + "%",
                        )  #|| used to flag this line in plog().



                    if (
                        quartileExposureReport == 0
                    ):  # Silly daft but workable exposure time reporting by MTF
                        initialRemaining = remaining
                        quartileExposureReport = quartileExposureReport + 1
                    if (
                        quartileExposureReport == 1
                        and remaining < initialRemaining * 0.75
                        and initialRemaining > 30
                    ):
                        quartileExposureReport = quartileExposureReport + 1
                        g_dev["obs"].send_to_user(
                            "Exposure 25% complete. Remaining: "
                            + str(remaining)
                            + " sec.",
                            p_level="INFO",
                        )
                        if (exposure_time > 120):
                            g_dev["obs"].request_update_status()

                    if (
                        quartileExposureReport == 2
                        and remaining < initialRemaining * 0.50
                        and initialRemaining > 30
                    ):
                        quartileExposureReport = quartileExposureReport + 1
                        g_dev["obs"].send_to_user(
                            "Exposure 50% complete. Remaining: "
                            + str(remaining)
                            + " sec.",
                            p_level="INFO",
                        )
                        if (exposure_time > 60):
                            g_dev["obs"].request_update_status()

                    if (
                        quartileExposureReport == 3
                        and remaining < initialRemaining * 0.25
                        and initialRemaining > 30
                    ):
                        quartileExposureReport = quartileExposureReport + 1
                        g_dev["obs"].send_to_user(
                            "Exposure 75% complete. Remaining: "
                            + str(remaining)
                            + " sec.",
                            p_level="INFO",
                        )
                        if remaining > 5 and not block_and_focus_check_done:
                            if g_dev['seq'].blockend != None:
                                g_dev['obs'].request_update_calendar_blocks()
                            block_and_focus_check_done=True

                    # Need to have a time sleep to release the GIL to run the other threads

                    if time.time() > (start_time_of_observation + exposure_time):
                        # If the exposure time has passed, then the shutter is closed for normal exposures
                        # The substacker thread reports the shutter_open(/closed). Other methods may not.
                        if not self.substacker:
                            g_dev['cam'].shutter_open=False
                        #else:

                    # If the shutter has closed but there is still time, then nudge the scope while reading out
                    if not g_dev['cam'].shutter_open:

                        # Attempt to sneak in a platesolve and nudge during readout time.
                        if not check_nudge_after_shutter_closed:
                            plog ("Shutter Closed.")

                            #self.running_an_exposure_set=False
                            # Immediately nudge scope to a different point in the smartstack dither except for the last frame and after the last frame.
                            if not g_dev['obs'].mountless_operation:

                                if g_dev['obs'].pointing_recentering_requested_by_platesolve_thread or g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                                    self.wait_for_slew()
                                    g_dev['obs'].check_platesolve_and_nudge()

                                # Don't nudge scope if it wants to correct the pointing or is slewing or there has been a pier flip.
                                elif self.dither_enabled and not g_dev['mnt'].pier_flip_detected and not g_dev['mnt'].currently_slewing and not g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                                    if Nsmartstack > 1 and not ((Nsmartstack == sskcounter+1) or (Nsmartstack == sskcounter+2)):
                                        #breakpoint()
                                        if (self.pixscale == None):
                                            ra_random_dither=(((random.randint(0,50)-25) * 0.75 / 3600 ) / 15)
                                            dec_random_dither=((random.randint(0,50)-25) * 0.75 /3600 )
                                        else:
                                            ra_random_dither=(((random.randint(0,50)-25) * self.pixscale / 3600 ) / 15)
                                            dec_random_dither=((random.randint(0,50)-25) * self.pixscale /3600 )
                                        try:
                                            self.wait_for_slew()
                                            g_dev['mnt'].slew_async_directly(ra=self.initial_smartstack_ra + ra_random_dither, dec=self.initial_smartstack_dec + dec_random_dither)
                                            # no wait for slew here as we start downloading the image. the wait_for_slew is after that

                                        except Exception as e:
                                            plog (traceback.format_exc())
                                            if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:

                                                plog("The SkyX had an error.")
                                                plog("Usually this is because of a broken connection.")
                                                plog("Killing then waiting 60 seconds then reconnecting")
                                                g_dev['seq'].kill_and_reboot_theskyx(g_dev['mnt'].current_icrs_ra,g_dev['mnt'].current_icrs_dec)

                                    # Otherwise immediately nudge scope back to initial pointing in smartstack after the last frame of the smartstack
                                    # Last frame of the smartstack must also be at the normal pointing for platesolving purposes
                                    elif Nsmartstack > 1 and ((Nsmartstack == sskcounter+1) or (Nsmartstack == sskcounter+2)):
                                        try:
                                            self.wait_for_slew()
                                            g_dev['mnt'].slew_async_directly(ra=self.initial_smartstack_ra, dec=self.initial_smartstack_dec)
                                            # no wait for slew here as we start downloading the image. the wait_for_slew is after that

                                        except Exception as e:
                                            plog (traceback.format_exc())
                                            if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:

                                                plog("The SkyX had an error.")
                                                plog("Usually this is because of a broken connection.")
                                                plog("Killing then waiting 60 seconds then reconnecting")
                                                g_dev['seq'].kill_and_reboot_theskyx(g_dev['mnt'].current_icrs_ra,g_dev['mnt'].current_icrs_dec)

                            # If this is the last set of something in an execute_block from the sequence (project calendar)
                            # Then get ready for the next set of exposures by changing the filter and adjusting the focus
                            # Hopefully this occurs while the slew occurs
                            # If there is a block guard, there is a running block
                            # print ('seq and count')
                            # print (seq)
                            # print (count)
                            if g_dev['seq'].block_guard and seq==count and not g_dev['seq'].focussing and not frame_type=='pointing':
                                # plog ("Running block....")
                                # plog (Nsmartstack)
                                # plog (sskcounter)
                                # If this is the end of a smartstack set or it is a single shot then check the filter and change
                                if Nsmartstack==1 or (Nsmartstack == sskcounter+1):
                                    # plog ("end of sstack run, checking filter")
                                    plog ("Next filter in project: " + str(g_dev['seq'].block_next_filter_requested))
                                    plog ("Current filter: " + str(self.current_filter))
                                    if not g_dev['seq'].block_next_filter_requested=='None':
                                        # Check if filter needs changing, if so, change.
                                        self.current_filter= g_dev['fil'].filter_selected
                                        if not self.current_filter == g_dev['seq'].block_next_filter_requested:
                                            plog ("Changing filter")
                                            self.current_filter, filt_pointer, filter_offset = g_dev["fil"].set_name_command(
                                                {"filter": g_dev['seq'].block_next_filter_requested}, {}
                                            )

                            check_nudge_after_shutter_closed=True

                        temp_time_sleep=min(self.completion_time - time.time()+0.00001, initialRemaining * 0.125)

                    else:
                        if time.time() < (start_time_of_observation + exposure_time):
                            temp_time_sleep=min(start_time_of_observation + exposure_time - time.time()+0.00001, initialRemaining * 0.125)


                    if temp_time_sleep > 0:
                        time.sleep(temp_time_sleep)

                continue

            elif self.async_exposure_lock == False and self._imageavailable():   #NB no more file-mode


                if self.shutter_open:
                    self.shutter_open=False
                    plog ("Shutter Closed.")

                plog ("Exposure Complete")
                g_dev["obs"].send_to_user("Exposure Complete")

                # If the nudge wasn't done during the readout, then nudge it now
                if not check_nudge_after_shutter_closed:
                    #self.running_an_exposure_set=False
                    # Immediately nudge scope to a different point in the smartstack dither except for the last frame and after the last frame.
                    if not g_dev['obs'].mountless_operation:

                        if g_dev['obs'].pointing_recentering_requested_by_platesolve_thread or g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                            self.wait_for_slew()
                            g_dev['obs'].check_platesolve_and_nudge()

                        # Don't nudge scope if it wants to correct the pointing or is slewing or there has been a pier flip.
                        elif self.dither_enabled and not g_dev['mnt'].pier_flip_detected and not g_dev['mnt'].currently_slewing and not g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                            if Nsmartstack > 1 and not ((Nsmartstack == sskcounter+1) or (Nsmartstack == sskcounter+2)):
                                #breakpoint()
                                if (self.pixscale == None):
                                    ra_random_dither=(((random.randint(0,50)-25) * 0.75 / 3600 ) / 15)
                                    dec_random_dither=((random.randint(0,50)-25) * 0.75 /3600 )
                                else:
                                    ra_random_dither=(((random.randint(0,50)-25) * self.pixscale / 3600 ) / 15)
                                    dec_random_dither=((random.randint(0,50)-25) * self.pixscale /3600 )
                                try:
                                    self.wait_for_slew()
                                    g_dev['mnt'].slew_async_directly(ra=self.initial_smartstack_ra + ra_random_dither, dec=self.initial_smartstack_dec + dec_random_dither)
                                    # no wait for slew here as we start downloading the image. the wait_for_slew is after that

                                except Exception as e:
                                    plog (traceback.format_exc())
                                    if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:

                                        plog("The SkyX had an error.")
                                        plog("Usually this is because of a broken connection.")
                                        plog("Killing then waiting 60 seconds then reconnecting")
                                        g_dev['seq'].kill_and_reboot_theskyx(g_dev['mnt'].current_icrs_ra,g_dev['mnt'].current_icrs_dec)

                            # Otherwise immediately nudge scope back to initial pointing in smartstack after the last frame of the smartstack
                            # Last frame of the smartstack must also be at the normal pointing for platesolving purposes
                            elif Nsmartstack > 1 and ((Nsmartstack == sskcounter+1) or (Nsmartstack == sskcounter+2)):
                                try:
                                    self.wait_for_slew()
                                    g_dev['mnt'].slew_async_directly(ra=self.initial_smartstack_ra, dec=self.initial_smartstack_dec)
                                    # no wait for slew here as we start downloading the image. the wait_for_slew is after that

                                except Exception as e:
                                    plog (traceback.format_exc())
                                    if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:

                                        plog("The SkyX had an error.")
                                        plog("Usually this is because of a broken connection.")
                                        plog("Killing then waiting 60 seconds then reconnecting")
                                        g_dev['seq'].kill_and_reboot_theskyx(g_dev['mnt'].current_icrs_ra,g_dev['mnt'].current_icrs_dec)
                    # If this is the last set of something in an execute_block from the sequence (project calendar)
                    # Then get ready for the next set of exposures by changing the filter and adjusting the focus
                    # Hopefully this occurs while the slew occurs
                    # If there is a block guard, there is a running block
                    if g_dev['seq'].block_guard and not g_dev['seq'].focussing and not frame_type=='pointing':
                        # plog ("Running block....")
                        # plog (Nsmartstack)
                        # plog (sskcounter)
                        # If this is the end of a smartstack set or it is a single shot then check the filter and change
                        if (Nsmartstack==1 or (Nsmartstack == sskcounter+1)) :#and not g_dev['seq'].focussing and not frame_type=='pointing':
                            # plog ("end of sstack run, checking filter")
                            plog ("Requested filter: " + str(g_dev['seq'].block_next_filter_requested))
                            plog ("Current filter: " + str(self.current_filter))
                            if not g_dev['seq'].block_next_filter_requested=='None':
                                # Check if filter needs changing, if so, change.
                                self.current_filter= g_dev['fil'].filter_selected
                                if not self.current_filter == g_dev['seq'].block_next_filter_requested:
                                    plog ("Changing filter")
                                    self.current_filter, filt_pointer, filter_offset = g_dev["fil"].set_name_command(
                                        {"filter": g_dev['seq'].block_next_filter_requested}, {}
                                    )


                if self.theskyx:
                    self.readout_estimate= time.time()-start_time_of_observation-exposure_time
                    plog ("Theskyx readout time: " + str(self.readout_estimate))

                if self.substacker:
                    expected_endpoint_of_substack_exposure=copy.deepcopy(self.expected_endpoint_of_substack_exposure)
                    substack_start_time=copy.deepcopy(self.substack_start_time)
                    sub_stacker_midpoints=copy.deepcopy(self.sub_stacker_midpoints)
                else:
                    expected_endpoint_of_substack_exposure=None
                    substack_start_time=None
                    sub_stacker_midpoints=None

                # If you are shooting for short exposure times, the overhead
                # becomes a large fraction of the actual exposure time,
                # sometimes more. So if it is a short exposure, assume nothing changed
                # much since the beginning.
                if exposure_time >= 5:
                    try:
                        g_dev["rot"].get_quick_status(self.post_rot)
                    except:
                        pass
                    try:
                        g_dev["foc"].get_quick_status(self.post_foc)
                    except:
                        pass
                    try:
                        g_dev["mnt"].get_rapid_exposure_status(
                            self.post_mnt
                        )  # Need to pick which pass was closest to image completion
                    except:
                        pass
                else:
                    self.post_rot = self.pre_rot
                    self.post_foc = self.pre_foc
                    self.post_mnt = self.pre_mnt


                imageCollected = 0
                retrycounter = 0
                while imageCollected != 1:
                    if retrycounter == 8:
                        expresult = {"error": True}
                        plog("Retried 8 times and didn't get an image, giving up.")
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        return expresult
                    try:
                        outputimg = self._getImageArray().astype(np.float32)
                        imageCollected = 1
                    except Exception as e:
                        plog(e)
                        plog (traceback.format_exc())
                        if "Image Not Available" in str(e):
                            plog("Still waiting for file to arrive: ", e)
                        time.sleep(3)
                        retrycounter = retrycounter + 1


                readout_estimate = copy.deepcopy(self.readout_estimate)
                # If there isn't an estimated readout time shelf yet, use this first one as the estimate to begin with.
                if self.readout_time==0:
                    self.readout_time=copy.deepcopy(readout_estimate)
                # Here is where we wait for any slew left over while async'ing and grabbing image
                if Nsmartstack > 1:
                    self.wait_for_slew()
                    g_dev['obs'].check_platesolve_and_nudge()


                if (frame_type in ["bias", "dark"]  or a_dark_exposure or frame_type[-4:] == ['flat']) and not manually_requested_calibration:
                    plog("Median of full-image area bias, dark or flat:  ", np.median(outputimg))

                    # Check that the temperature is ok before accepting
                    current_camera_temperature, cur_humidity, cur_pressure = (g_dev['cam']._temperature())
                    current_camera_temperature = float(current_camera_temperature)
                    if abs(float(current_camera_temperature) - float(g_dev['cam'].setpoint)) > 1.5:   #NB NB this might best be a config item.
                        plog ("temperature out of range for calibrations ("+ str(current_camera_temperature)+"), rejecting calibration frame")
                        g_dev['obs'].camera_sufficiently_cooled_for_calibrations = False
                        expresult = {}
                        expresult["error"] = True
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        return expresult

                    else:
                        plog ("temperature in range for calibrations ("+ str(current_camera_temperature)+"), accepting calibration frame")
                        g_dev['obs'].camera_sufficiently_cooled_for_calibrations = True

                    # For a dark, check that the debiased dark has an adequately low value
                    # If there is no master bias, it will just skip this check
                    if frame_type in ["dark"]  or a_dark_exposure :
                        dark_limit_adu =   self.config["camera"][self.name]["settings"]['dark_lim_adu']
                        if len(self.biasFiles) > 0:
                            tempcrop=int(min(outputimg.shape)*0.15)

                            tempmodearray=((outputimg[tempcrop:-tempcrop, tempcrop:-tempcrop] - self.biasFiles[str(1)][tempcrop:-tempcrop, tempcrop:-tempcrop]) *10)
                            int_array_flattened=tempmodearray.astype(int).ravel()
                            unique,counts=np.unique(int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
                            m=counts.argmax()
                            imageMode=unique[m]
                            debiaseddarkmode= imageMode / 10 / exposure_time
                            plog ("Debiased 1s Dark Mode is " + str(debiaseddarkmode))

                            debiaseddarkmedian= bn.nanmedian(outputimg[tempcrop:-tempcrop, tempcrop:-tempcrop] - self.biasFiles[str(1)][tempcrop:-tempcrop, tempcrop:-tempcrop]) / exposure_time
                            plog ("Debiased 1s Dark Median is " + str(debiaseddarkmedian))

                            debiaseddarkmean= bn.nanmean(outputimg[tempcrop:-tempcrop, tempcrop:-tempcrop] - self.biasFiles[str(1)][tempcrop:-tempcrop, tempcrop:-tempcrop]) / exposure_time
                            plog ("Debiased 1s Dark Mean is " + str(debiaseddarkmean))

                            plog ("Exposure time: " + str(exposure_time))
                            #breakpoint()
                            #Short exposures are inherently much more variable, so their limit is set much higher.

                            if frame_type in ['pointzerozerofourfive_exposure_dark','onepointfivepercent_exposure_dark','fivepercent_exposure_dark','tenpercent_exposure_dark']:
                                plog ("This exposure is too short for the dark rejecter to be particularly reliable.")
                            elif frame_type in ['quartersec_exposure_dark', 'halfsec_exposure_dark','threequartersec_exposure_dark','onesec_exposure_dark', 'oneandahalfsec_exposure_dark', 'twosec_exposure_dark']:
                                if debiaseddarkmedian > 10*dark_limit_adu:   # was 0.5, NB later add in an std based second rejection criterion
                                    plog ("Reject! This Dark seems to be light affected. ")
                                    expresult = {}
                                    expresult["error"] = True
                                    # self.running_an_exposure_set = False
                                    # self.shutter_open=False
                                    return expresult
                            elif debiaseddarkmedian > dark_limit_adu:   # was 0.5, NB later add in an std based second rejection criterion
                                plog ("Reject! This Dark seems to be light affected. ")
                                expresult = {}
                                expresult["error"] = True
                                # self.running_an_exposure_set = False
                                # self.shutter_open=False
                                return expresult







                try:
                    next_seq = next_sequence(self.config["camera"][self.name]["name"])
                except:
                    next_seq = reset_sequence(self.config["camera"][self.name]["name"])


                self.next_seq= next_seq


                # HERE IS WHERE WE SPIT OUT THE FILES INTO A MULTIPROCESSING FUNCTION
                if not g_dev['obs'].mountless_operation:
                    avg_mnt = g_dev["mnt"].get_average_status(self.pre_mnt, self.post_mnt)
                else:
                    avg_mnt = None
                try:
                    avg_foc = g_dev["foc"].get_average_status(self.pre_foc, self.post_foc)
                except:
                    pass
                try:
                    avg_rot = g_dev["rot"].get_average_status(
                        self.pre_rot, self.post_rot
                    )
                except:
                    avg_rot = None

                object_name='Unknown'
                object_specf='no'

                if "object_name" in opt:
                    if (
                        opt["object_name"] != "Unspecified"
                        and opt["object_name"] != ""
                    ):
                        object_name = opt["object_name"]
                        object_specf = "yes"
                elif (
                    g_dev["mnt"].object != "Unspecified"
                    or g_dev["mnt"].object != "empty"
                ):
                    object_name = (g_dev["mnt"].object, "Object name")
                    object_specf = "yes"
                else:
                    RAtemp = g_dev["mnt"].current_icrs_ra
                    DECtemp = g_dev["mnt"].current_icrs_dec
                    RAstring = f"{RAtemp:.1f}".replace(".", "h")
                    DECstring = f"{DECtemp:.1f}".replace("-", "n").replace(".", "d")
                    object_name = RAstring + "ra" + DECstring + "dec"
                    object_specf = "no"

                # If NOT an expose image going into the post-process thread, rotate the fits here.
                if not(not frame_type[-4:] == "flat" and not frame_type in ["bias", "dark"] and not a_dark_exposure and not focus_image and not frame_type=='pointing'):
                    # Flip flat fits around to correct orientation
                    if self.config["camera"][self.name]["settings"]["transpose_fits"]:
                        outputimg=outputimg.transpose().astype('float32')
                    elif self.config["camera"][self.name]["settings"]["flipx_fits"]:
                        outputimg=np.fliplr(outputimg.astype('float32')
                        )
                    elif self.config["camera"][self.name]["settings"]["flipy_fits"]:
                        outputimg=np.flipud(outputimg.astype('float32')
                        )
                    elif self.config["camera"][self.name]["settings"]["rotate90_fits"]:
                        outputimg=np.rot90(outputimg.astype('float32')
                        )
                    elif self.config["camera"][self.name]["settings"]["rotate180_fits"]:
                        outputimg=np.rot90(outputimg.astype('float32'),2)

                    elif self.config["camera"][self.name]["settings"]["rotate270_fits"]:
                        outputimg= np.rot90(outputimg.astype('float32'),3)

                    else:
                        outputimg=outputimg.astype('float32')

                # Specific dark and bias save area
                if (frame_type in ["bias", "dark"] or a_dark_exposure) and not manually_requested_calibration:
                    # Save good flat
                    im_path_r = self.camera_path
                    raw_path = im_path_r + g_dev["day"] + "/raw/"

                    raw_name00 = (
                        self.config["obs_id"]
                        + "-"
                        + g_dev['cam'].alias + '_' + str(frame_type.replace('_','')) + '_' + str(this_exposure_filter)
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + "-"
                        + "skyflat"
                        + "00.fits"
                    )

                    hdu = fits.PrimaryHDU()
                    hdu = fits.PrimaryHDU(
                            outputimg.astype('float32')
                        )
                    del outputimg


                    hdu.header['PIXSCALE']=self.pixscale
                    hdu.header['EXPTIME']=exposure_time

                    hdu.header['OBSTYPE']='flat'
                    hdu.header['FILTER']=self.current_filter


                    # If the files are local calibrations, save them out to the local calibration directory
                    if not manually_requested_calibration:
                        if not g_dev['obs'].mountless_operation:
                            g_dev['obs'].to_slow_process(200000000, ('localcalibration', copy.deepcopy(raw_name00), copy.deepcopy(hdu.data), copy.deepcopy(hdu.header), copy.deepcopy(frame_type), copy.deepcopy(g_dev["mnt"].current_icrs_ra), copy.deepcopy(g_dev["mnt"].current_icrs_dec)))
                        else:
                            g_dev['obs'].to_slow_process(200000000, ('localcalibration', copy.deepcopy(raw_name00), copy.deepcopy(hdu.data), copy.deepcopy(hdu.header), copy.deepcopy(frame_type), None, None))


                    # Make  sure the alt paths exist
                    if g_dev['obs'].config["save_to_alt_path"] == "yes":
                        # os.makedirs(
                        #     g_dev['obs'].alt_path + g_dev["day"], exist_ok=True
                        # )
                        # os.makedirs(
                        #     g_dev['obs'].alt_path + g_dev["day"] + "/raw/", exist_ok=True
                        # )
                        # os.makedirs(
                        #     g_dev['obs'].alt_path + g_dev["day"] + "/reduced/", exist_ok=True
                        # )
                        # os.makedirs(
                        #     g_dev['obs'].alt_path + g_dev["day"] + "/calib/", exist_ok=True)



                        altpath=copy.deepcopy(g_dev['obs'].alt_path)
                    else:
                        altpath='no'



                    # Similarly to the above. This saves the RAW file to disk
                    if self.config['save_raw_to_disk']:

                        # Make sure the raw paths exist
                        im_path_r = self.camera_path
                        raw_path = im_path_r + g_dev["day"] + "/raw/"
                        os.makedirs(
                            self.camera_path + g_dev["day"], exist_ok=True
                        )

                        os.makedirs(
                            raw_path, exist_ok=True
                        )

                        #g_dev['obs'].to_slow_process(1000,('raw', raw_path + raw_name00, hdu.data, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))
                        threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw', raw_path + raw_name00, hdu.data, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec,altpath,'deprecated')),)).start()


                    # For sites that have "save_to_alt_path" enabled, this routine
                    # Saves the raw and reduced fits files out to the provided directories
                    if self.config["save_to_alt_path"] == "yes":
                        self.alt_path = self.config[
                            "alt_path"
                        ]  +'/' + self.config['obs_id']+ '/' # NB NB this should come from config file, it is site dependent.

                        # g_dev['obs'].to_slow_process(1000,('raw_alt_path', self.alt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header, \
                        #                                frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))


                        os.makedirs(
                            self.alt_path , exist_ok=True
                        )

                        os.makedirs(
                            self.alt_path + g_dev["day"], exist_ok=True
                        )

                        os.makedirs(
                           self.alt_path + g_dev["day"] + "/raw/" , exist_ok=True
                        )
                        threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw_alt_path', self.alt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header, \
                                                       frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec,altpath,'deprecated')),)).start()


                    del hdu
                    #self.running_an_exposure_set = False
                    return copy.deepcopy(expresult)



                if not frame_type[-4:] == "flat" and not frame_type in ["bias", "dark"]  and not a_dark_exposure and not focus_image and not frame_type=='pointing':
                    focus_position=g_dev['foc'].current_focus_position


                    self.post_processing_queue.put(copy.deepcopy((outputimg, g_dev["mnt"].pier_side, self.config["camera"][self.name]["settings"]['is_osc'], frame_type, self.config['camera']['camera_1_1']['settings']['reject_new_flat_by_known_gain'], avg_mnt, avg_foc, avg_rot, self.setpoint, self.tempccdtemp, self.ccd_humidity, self.ccd_pressure, self.darkslide_state, exposure_time, this_exposure_filter, exposure_filter_offset, self.pane,opt , observer_user_name, self.hint, azimuth_of_observation, altitude_of_observation, airmass_of_observation, self.pixscale, smartstackid,sskcounter,Nsmartstack, 'longstack_deprecated', ra_at_time_of_exposure, dec_at_time_of_exposure, manually_requested_calibration, object_name, object_specf, g_dev["mnt"].ha_corr, g_dev["mnt"].dec_corr, focus_position, self.config, self.name, self.camera_known_gain, self.camera_known_readnoise, start_time_of_observation, observer_user_id, self.camera_path,  solve_it, next_seq, zoom_factor, useastrometrynet, self.substacker,expected_endpoint_of_substack_exposure,substack_start_time,readout_estimate, self.readout_time, sub_stacker_midpoints)), block=False)


                # If this is a pointing or a focus frame, we need to do an
                # in-line flash reduction
                if (frame_type=='pointing' or focus_image == True) and not self.substacker:
                    # Make sure any dither or return nudge has finished before platesolution
                    try:

                        # timetakenquickdark=time.time()
                        # If not a smartstack use a scaled masterdark
                        #if self.substack
                        if smartstackid == 'no':
                            # Initially debias the image
                            outputimg = outputimg - g_dev['cam'].biasFiles[str(1)]
                            outputimg=outputimg-(intermediate_tempdark*exposure_time)
                            del intermediate_tempdark
                        elif exposure_time == broadband_ss_biasdark_exp_time:
                            outputimg = outputimg - (g_dev['cam'].darkFiles['broadband_ss_biasdark'])
                            #plog ("broadband biasdark success")
                        elif exposure_time == narrowband_ss_biasdark_exp_time:
                            outputimg = outputimg - (g_dev['cam'].darkFiles['narrowband_ss_biasdark'])
                            #plog ("narrowband biasdark success")
                        else:
                            plog ("DUNNO WHAT HAPPENED!")
                            outputimg = outputimg - g_dev['cam'].biasFiles[str(1)]
                            outputimg = outputimg - (g_dev['cam'].darkFiles[str(1)] * exposure_time)
                        # plog ("time taken quickdark")
                        # plog (str(time.time() - timetakenquickdark))
                    except Exception as e:
                        plog("debias/darking light frame failed: ", e)

                    # Quick flat flat frame
                    try:
                        #plog ("FLATTERY")
                        # if self.config['camera'][self.name]['settings']['hold_flats_in_memory']:
                        #     outputimg = np.divide(outputimg, g_dev['cam'].flatFiles[g_dev['cam'].current_filter])
                        # else:
                        #outputimg = np.divide(outputimg, np.load(g_dev['cam'].flatFiles[str(g_dev['cam'].current_filter + "_bin" + str(1))]))
                        outputimg = np.divide(outputimg, intermediate_tempflat)
                        #intermediate_tempflat
                    except Exception as e:
                        plog("flatting light frame failed", e)

                    try:
                        outputimg[g_dev['cam'].bpmFiles[str(1)]] = np.nan

                    except Exception as e:
                        plog("applying bad pixel mask to light frame failed: ", e)

                    # # Fast next-door-neighbour in-fill algorithm
                    # bpmtime=time.time()
                    # num_of_nans=np.count_nonzero(np.isnan(outputimg))
                    # while num_of_nans > 0:
                    #     # List the coordinates that are nan in the array
                    #     nan_coords=np.argwhere(np.isnan(outputimg))
                    #     x_size=outputimg.shape[0]
                    #     y_size=outputimg.shape[1]
                    #     # For each coordinate try and find a non-nan-neighbour and steal its value
                    #     try:
                    #         for nancoord in nan_coords:
                    #             x_nancoord=nancoord[0]
                    #             y_nancoord=nancoord[1]
                    #             # left
                    #             done=False
                    #             #NB NB WER: Here I would do a median-8, except at edges.
                    #             #That will first-order also deal with Telegraph Noise.
                    #             #Second the substitue pixel will be less correlated with its neighbors.
                    #             #NB NB MTF: That is too slow. Here we are just making a reduced image
                    #             # As quick as possible to extract what we need -- FWHM.
                    #             # This is happening in-line rather than a subprocess, so the faster the better.
                    #             if x_nancoord != 0:
                    #                 value_here=outputimg[x_nancoord-1,y_nancoord]
                    #                 if not np.isnan(value_here):
                    #                     outputimg[x_nancoord,y_nancoord]=value_here
                    #                     done=True
                    #             # right
                    #             if not done:
                    #                 if x_nancoord != (x_size-1):
                    #                     value_here=outputimg[x_nancoord+1,y_nancoord]
                    #                     if not np.isnan(value_here):
                    #                         outputimg[x_nancoord,y_nancoord]=value_here
                    #                         done=True
                    #             # below
                    #             if not done:
                    #                 if y_nancoord != 0:
                    #                     value_here=outputimg[x_nancoord,y_nancoord-1]
                    #                     if not np.isnan(value_here):
                    #                         outputimg[x_nancoord,y_nancoord]=value_here
                    #                         done=True
                    #             # above
                    #             if not done:
                    #                 if y_nancoord != (y_size-1):
                    #                     value_here=outputimg[x_nancoord,y_nancoord+1]
                    #                     if not np.isnan(value_here):
                    #                         outputimg[x_nancoord,y_nancoord]=value_here
                    #                         done=True
                    #     except:
                    #         plog(traceback.format_exc())
                    #         #breakpoint()
                    #     num_of_nans=np.count_nonzero(np.isnan(outputimg))
                    # plog ("bad pixel time monitor " + str(time.time()-bpmtime))



                if frame_type=='pointing' and focus_image == False:


                    im_path_r = self.camera_path
                    im_type = "EX"
                    f_ext = "-"
                    cal_name = (
                        self.config["obs_id"]
                        + "-"
                        + self.config["camera"][self.name]["name"]
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + f_ext
                        + "-"
                        + im_type
                        + "00.fits"
                    )
                    cal_path = im_path_r + g_dev["day"] + "/calib/"

                    if not os.path.exists(im_path_r):
                        os.makedirs(im_path_r)
                    if not os.path.exists(im_path_r+ g_dev["day"]):
                        os.makedirs(im_path_r+ g_dev["day"])
                    if not os.path.exists(im_path_r+ g_dev["day"]+ "/calib"):
                        os.makedirs(im_path_r+ g_dev["day"]+ "/calib")
                    if not os.path.exists(im_path_r+ g_dev["day"] + "/to_AWS"):
                        os.makedirs(im_path_r+ g_dev["day"]+ "/to_AWS")

                    hdu = fits.PrimaryHDU()
                    if np.isnan(self.pixscale) or self.pixscale==None:
                        plog ("no pixelscale available")
                    else:
                        hdu.header['PIXSCALE']=self.pixscale

                    hdu.header['OBSTYPE']='pointing'
                    hdusmallheader=copy.deepcopy(hdu.header)
                    del hdu

                    g_dev['obs'].platesolve_is_processing =True
                    g_dev['obs'].to_platesolve((outputimg, hdusmallheader, cal_path, cal_name, frame_type, time.time(), self.pixscale, ra_at_time_of_exposure,dec_at_time_of_exposure, False, useastrometrynet))



                # If this is a focus image, we need to wait until the SEP queue is finished and empty to pick up the latest
                # FWHM.
                if focus_image == True:
                    im_path_r = self.camera_path
                    im_type = "EX"
                    f_ext = "-"
                    text_name = (
                        self.config["obs_id"]
                        + "-"
                        + self.config["camera"][self.name]["name"]
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + "-"
                        + im_type
                        + "00.txt"
                    )
                    im_path = im_path_r + g_dev["day"] + "/to_AWS/"
                    cal_name = (
                        self.config["obs_id"]
                        + "-"
                        + self.config["camera"][self.name]["name"]
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + f_ext
                        + "-"
                        + im_type
                        + "00.fits"
                    )
                    cal_path = im_path_r + g_dev["day"] + "/calib/"

                    if not os.path.exists(im_path_r):
                        os.makedirs(im_path_r)
                    if not os.path.exists(im_path_r+ g_dev["day"]):
                        os.makedirs(im_path_r+ g_dev["day"])
                    if not os.path.exists(im_path_r+ g_dev["day"]+ "/calib"):
                        os.makedirs(im_path_r+ g_dev["day"]+ "/calib")
                    if not os.path.exists(im_path_r+ g_dev["day"] + "/to_AWS"):
                        os.makedirs(im_path_r+ g_dev["day"]+ "/to_AWS")



                    hdu = fits.PrimaryHDU()
                    try:
                        hdu.header['PIXSCALE']=self.pixscale
                    except:
                        hdu.header['PIXSCALE']=-99
                    hdu.header['EXPTIME']=exposure_time

                    hdu.header['OBSTYPE']='focus'
                    hdu.header["SITEID"] = (self.config["wema_name"].replace("-", "").replace("_", ""))
                    hdu.header["INSTRUME"] = (self.config["camera"][self.name]["name"], "Name of camera")
                    hdu.header["DAY-OBS"] = (
                        g_dev["day"],
                        "Date at start of observing night"
                    )
                    raw_name00 = (
                        self.config["obs_id"]
                        + "-"
                        + self.config["camera"][self.name]["name"] + '_' + str(frame_type) + '_' + str(this_exposure_filter)
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + "-"
                        + im_type
                        + "00.fits"
                    )
                    hdu.header["ORIGNAME"] = str(raw_name00 + ".fz")
                    hdu.header["FILTER"] =g_dev['cam'].current_filter
                    hdu.header["SMARTSTK"] = 'no'
                    hdu.header["SSTKNUM"] = 1
                    hdu.header["SUBSTACK"] = self.substacker

                    tempRAdeg = ra_at_time_of_exposure * 15
                    tempDECdeg = dec_at_time_of_exposure
                    tempointing = SkyCoord(tempRAdeg, tempDECdeg, unit='deg')
                    tempointing=tempointing.to_string("hmsdms").split(' ')

                    hdu.header["RA"] = (
                        tempointing[0],
                        "[hms] Telescope right ascension",
                    )
                    hdu.header["DEC"] = (
                        tempointing[1],
                        "[dms] Telescope declination",
                    )
                    hdu.header["AZIMUTH "] = (
                        azimuth_of_observation,
                        "[deg] Azimuth axis positions",
                    )
                    hdu.header["ALTITUDE"] = (
                        altitude_of_observation,
                        "[deg] Altitude axis position",
                    )
                    hdu.header["ZENITH"] = (90 - altitude_of_observation, "[deg] Zenith")
                    hdu.header["AIRMASS"] = (
                        airmass_of_observation,
                        "Effective mean airmass",
                    )

                    hdusmallheader=copy.deepcopy(hdu.header)
                    del hdu
                    focus_position=g_dev['foc'].current_focus_position
                    #g_dev['obs'].sep_processing=True
                    #g_dev['obs'].to_sep((outputimg, self.pixscale, self.camera_known_readnoise, avg_foc[1], focus_image, im_path, text_name, hdusmallheader, cal_path, cal_name, frame_type, focus_position, self.native_bin))

                    #reported=0
                    #temptimer=time.time()

                    # while True:
                    #     if g_dev['obs'].sep_processing==False and g_dev['obs'].sep_queue.empty():
                    #         break
                    #     else:
                    #         if reported ==0:
                    #             plog ("FOCUS: Waiting for SEP processing to complete and queue to clear")
                    #             reported=1
                    #         pass

                    #         if g_dev['obs'].open_and_enabled_to_observe==False:
                    #             plog ("No longer open and enabled to observe, cancelling out of waiting for SEP.")
                    #             break

                    #     time.sleep(0.2)

                    # Instead of waiting for the photometry process we quickly measure the FWHM
                    # in-line. Necessary particularly because the photometry subprocess can bank up.
                    fwhm_dict = self.in_line_quick_focus(outputimg, im_path, text_name)
                    self.focus_next_seq = next_seq


                    #print ("focus analysis time: " + str(time.time() - temptimer))
                    focus_image = False
                    #breakpoint()

                    g_dev['obs'].fwhmresult['FWHM']=float(fwhm_dict['rfr'])
                    g_dev['obs'].fwhmresult['No_of_sources']= float(fwhm_dict['sources'])
                    #foc_pos1 = g_dev['obs'].fwhmresult['mean_focus']
                    #foc_pos1=focus_position

                    expresult['FWHM']=g_dev['obs'].fwhmresult['FWHM'] #fwhm_dict['rfr']
                    expresult["mean_focus"]=focus_position
                    expresult['No_of_sources']=fwhm_dict['sources']

                    plog ("Focus at " + str(focus_position) + " is " + str(round(float(g_dev['obs'].fwhmresult['FWHM']),2)))



                    try:
                        #hduheader["SEPSKY"] = str(sepsky)
                        hdusmallheader["SEPSKY"] = str(fwhm_dict['sky'])
                    except:
                        hdusmallheader["SEPSKY"] = -9999
                    try:
                        hdusmallheader["FWHM"] = (float(fwhm_dict['rfp'],2), 'FWHM in pixels')
                        hdusmallheader["FWHMpix"] = (float(fwhm_dict['rfp'],2), 'FWHM in pixels')
                    except:
                        hdusmallheader["FWHM"] = (-99, 'FWHM in pixels')
                        hdusmallheader["FWHMpix"] = (-99, 'FWHM in pixels')

                    try:
                        hdusmallheader["FWHMasec"] = (float(fwhm_dict['rfr'],2), 'FWHM in arcseconds')
                    except:
                        hdusmallheader["FWHMasec"] = (-99, 'FWHM in arcseconds')
                    try:
                        hdusmallheader["FWHMstd"] = (float(fwhm_dict['rfs'],2), 'FWHM standard deviation in arcseconds')
                    except:

                        hdusmallheader["FWHMstd"] = ( -99, 'FWHM standard deviation in arcseconds')

                    try:
                        hdusmallheader["NSTARS"] = ( str(fwhm_dict['sources']), 'Number of star-like sources in image')
                    except:
                        hdusmallheader["NSTARS"] = ( -99, 'Number of star-like sources in image')



                    if self.config['keep_focus_images_on_disk']:
                        g_dev['obs'].to_slow_process(1000, ('focus', cal_path + cal_name, outputimg, hdusmallheader,
                                                            frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                        if self.config["save_to_alt_path"] == "yes":
                            g_dev['obs'].to_slow_process(1000, ('raw_alt_path', self.alt_path + g_dev["day"] + "/calib/" + cal_name, outputimg, hdusmallheader,
                                                                frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))


                    #breakpoint()
                    try:
                        text = open(
                            im_path + text_name, "w"
                        )
                        text.write(str(hdusmallheader))
                        text.close()
                    except:
                        plog("Failed to write out focus text up for some reason")
                        plog(traceback.format_exc())




                    if os.path.exists(im_path + text_name):
                        try:
                            #g_dev['obs'].enqueue_for_fastUI(10, im_path, text_name)
                            g_dev['obs'].enqueue_for_fastUI(10, im_path, text_name)

                        except:
                            plog("Failed to send FOCUS TEXT up for some reason")
                            plog(traceback.format_exc())
                    #self.running_an_exposure_set = False
                    return expresult

                blockended=False
                # Check that the block isn't ending during normal observing time (don't check while biasing, flats etc.)
                if g_dev['seq'].blockend != None: # Only do this check if a block end was provided.

                # Check that the exposure doesn't go over the end of a block
                    endOfExposure = datetime.datetime.utcnow() + datetime.timedelta(seconds=exposure_time)
                    now_date_timeZ = endOfExposure.isoformat().split('.')[0] +'Z'

                    #plog (now_date_timeZ)
                    #plog (g_dev['seq'].blockend)

                    blockended = now_date_timeZ  >= g_dev['seq'].blockend

                    #plog (blockended)

                    if blockended or ephem.Date(ephem.now()+ (exposure_time *ephem.second)) >= \
                        g_dev['events']['End Morn Bias Dark']:
                        plog ("Exposure overlays the end of a block or the end of observing. Skipping Exposure.")
                        plog ("And Cancelling SmartStacks.")
                        Nsmartstack=1
                        sskcounter=2
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        self.currently_in_smartstack_loop=False


                # Good spot to check if we need to nudge the telescope
                # Allowed to on the last loop of a smartstack
                # We need to clear the nudge before putting another platesolve in the queue
                if (Nsmartstack > 1 and (Nsmartstack == sskcounter+1))  :
                    self.currently_in_smartstack_loop=False
                g_dev['obs'].check_platesolve_and_nudge()




                if frame_type[-4:] == "flat":
                    image_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]
                    if self.config["camera"][self.name]["settings"]['is_osc']:
                        temp_is_osc=True
                        osc_fits=copy.deepcopy(outputimg)

                        debayered=[]
                        max_median=0

                        debayered.append(osc_fits[::2, ::2])
                        debayered.append(osc_fits[::2, 1::2])
                        debayered.append(osc_fits[1::2, ::2])
                        debayered.append(osc_fits[1::2, 1::2])

                        # crop each of the images to the central region
                        oscounter=0
                        for oscimage in debayered:
                            cropx = int( (oscimage.shape[0] -500)/2)
                            cropy = int((oscimage.shape[1] -500) /2)
                            oscimage=oscimage[cropx:-cropx, cropy:-cropy]
                            oscmedian=bn.nanmedian(oscimage)
                            if oscmedian > max_median:
                                max_median=copy.deepcopy(oscmedian)
                                brightest_bayer=copy.deepcopy(oscounter)
                            oscounter=oscounter+1

                        del osc_fits
                        del debayered

                        central_median=max_median

                    else:
                        temp_is_osc=False
                        osc_fits=copy.deepcopy(outputimg)
                        cropx = int( (osc_fits.shape[0] -500)/2)
                        cropy = int((osc_fits.shape[1] -500) /2)
                        osc_fits=osc_fits[cropx:-cropx, cropy:-cropy]
                        central_median=bn.nanmedian(osc_fits)
                        del osc_fits

                    if (
                        central_median
                        >= 0.80* image_saturation_level
                    ):
                        plog("Flat rejected, center is too bright:  ", central_median)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too bright.", p_level="INFO"
                        )
                        expresult={}
                        expresult["error"] = True
                        expresult["patch"] = central_median
                        expresult["camera_gain"] = np.nan
                        # self.running_an_exposure_set = False

                        return copy.deepcopy(expresult) # signals to flat routine image was rejected, prompt return

                    elif (
                        central_median
                        <= 0.25 * image_saturation_level
                    ) and not temp_is_osc:
                        plog("Flat rejected, center is too dim:  ", central_median)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too dim.", p_level="INFO"
                        )
                        expresult={}
                        expresult["error"] = True
                        expresult["patch"] = central_median
                        expresult["camera_gain"] = np.nan
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        return copy.deepcopy(expresult)  # signals to flat routine image was rejected, prompt return
                    elif (
                        central_median
                        <= 0.5 * image_saturation_level
                    ) and temp_is_osc:
                        plog("Flat rejected, center is too dim:  ", central_median)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too dim.", p_level="INFO"
                        )
                        expresult={}
                        expresult["error"] = True
                        expresult["patch"] = central_median
                        expresult["camera_gain"] = np.nan
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        return copy.deepcopy(expresult) # signals to flat routine image was rejected, prompt return
                    else:
                        expresult={}
                        # Now estimate camera gain.
                        camera_gain_estimate_image=copy.deepcopy(outputimg)

                        try:

                            # Get the brightest bayer layer for gains
                            if self.config["camera"][self.name]["settings"]['is_osc']:
                                if brightest_bayer == 0:
                                    camera_gain_estimate_image=camera_gain_estimate_image[::2, ::2]
                                elif brightest_bayer == 1:
                                    camera_gain_estimate_image=camera_gain_estimate_image[::2, 1::2]
                                elif brightest_bayer == 2:
                                    camera_gain_estimate_image=camera_gain_estimate_image[1::2, ::2]
                                elif brightest_bayer == 3:
                                    camera_gain_estimate_image=camera_gain_estimate_image[1::2, 1::2]

                            cropx = int( (camera_gain_estimate_image.shape[0] -500)/2)
                            cropy = int((camera_gain_estimate_image.shape[1] -500) /2)
                            camera_gain_estimate_image=camera_gain_estimate_image[cropx:-cropx, cropy:-cropy]
                            camera_gain_estimate_image = sigma_clip(camera_gain_estimate_image, masked=False, axis=None)

                            cge_median=bn.nanmedian(camera_gain_estimate_image)
                            cge_stdev=np.nanstd(camera_gain_estimate_image)
                            cge_sqrt=pow(cge_median,0.5)
                            cge_gain=1/pow(cge_sqrt/cge_stdev, 2)


                            # We should only check whether the gain is good IF we have a good gain.
                            commissioning_flats=False

                            # Check if we have MOST of the flats we need
                            if os.path.exists(g_dev['obs'].local_flat_folder + g_dev['cam'].current_filter):
                                files_in_folder=glob.glob(g_dev['obs'].local_flat_folder + g_dev['cam'].current_filter + '/' + '*.n*')
                                files_in_folder= [ x for x in files_in_folder if "tempcali" not in x ]
                                max_files = self.config['camera']['camera_1_1']['settings']['number_of_flat_to_store']
                                n_files = len(files_in_folder)
                                if not ((n_files/max_files) > 0.8):
                                    commissioning_flats=True
                            else:
                                commissioning_flats=True

                            # If we don't have a good gain yet, we are commissioning
                            if g_dev['seq'].current_filter_last_camera_gain > 50:
                                commissioning_flats=True


                            # low values SHOULD be ok.
                            if commissioning_flats:
                                g_dev["obs"].send_to_user('Good flat value:  ' +str(int(central_median)) + ' Good Gain: ' + str(round(cge_gain,2)))
                                plog('Good flat value:  ' +str(central_median) + ' Not testing gain until flats in commissioned mode.')

                            elif cge_gain < (g_dev['seq'].current_filter_last_camera_gain + 3 *g_dev['seq'].current_filter_last_camera_gain_stdev):
                                g_dev["obs"].send_to_user('Good flat value:  ' +str(int(central_median)) + ' Good Gain: ' + str(round(cge_gain,2)))
                                plog('Good flat value:  ' +str(central_median) + ' Good Gain: ' + str(cge_gain))

                            elif (not self.config['camera']['camera_1_1']['settings']['reject_new_flat_by_known_gain']):
                                g_dev["obs"].send_to_user('Good flat value:  ' +str(int(central_median)) + ' Bad Gain: ' + str(round(cge_gain,2)) + ' Flat rejection by gain is off.')
                                plog('Good flat value:  ' +str(central_median) + ' Bad Gain: ' + str(cge_gain) + ' Flat rejection by gain is off.')

                            else:
                                g_dev["obs"].send_to_user('Good flat value:  ' +str(int(central_median)) + ' Bad Gain: ' + str(round(cge_gain,2)) + ' Flat rejected.')
                                plog('Good flat value:  ' +str(central_median) + ' Bad Gain: ' + str(cge_gain) + ' Flat rejected.')
                                expresult={}
                                expresult["error"] = True
                                expresult["patch"] = central_median
                                expresult["camera_gain"] = np.nan
                                # self.running_an_exposure_set = False
                                # self.shutter_open=False
                                return copy.deepcopy(expresult) # signals to flat routine image was rejected, prompt return

                            expresult["camera_gain"] = cge_gain


                        except Exception as e:
                            plog("Could not estimate the camera gain from this flat.")
                            plog(e)
                            expresult["camera_gain"] = np.nan
                        del camera_gain_estimate_image
                        expresult["error"] = False
                        expresult["patch"] = central_median
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        # plog("Exposure Complete")
                        # g_dev["obs"].send_to_user("Exposure Complete")


                        # Save good flat
                        im_path_r = self.camera_path
                        raw_path = im_path_r + g_dev["day"] + "/raw/"
                        raw_name00 = (
                            self.config["obs_id"]
                            + "-"
                            + g_dev['cam'].alias + '_' + str(frame_type) + '_' + str(this_exposure_filter)
                            + "-"
                            + g_dev["day"]
                            + "-"
                            + next_seq
                            + "-"
                            + "skyflat"
                            + "00.fits"
                        )
                        # if self.config['save_reduced_file_numberid_first']:
                        #     red_name01 = (next_seq + "-" +self.config["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(hdu.header['FILTER']) + "-" +  str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")
                        # else:
                        #     red_name01 = (self.config["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(hdu.header['FILTER']) + "-" + next_seq+ "-" + str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")


                        hdu = fits.PrimaryHDU()



                        # Flip flat fits around to correct orientation
                        if self.config["camera"][self.name]["settings"]["transpose_fits"]:
                            hdu = fits.PrimaryHDU(
                                outputimg.transpose().astype('float32'))
                        elif self.config["camera"][self.name]["settings"]["flipx_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.fliplr(outputimg.astype('float32'))
                            )
                        elif self.config["camera"][self.name]["settings"]["flipy_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.flipud(outputimg.astype('float32'))
                            )
                        elif self.config["camera"][self.name]["settings"]["rotate90_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.rot90(outputimg.astype('float32'))
                            )
                        elif self.config["camera"][self.name]["settings"]["rotate180_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.rot90(outputimg.astype('float32'),2)
                            )
                        elif self.config["camera"][self.name]["settings"]["rotate270_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.rot90(outputimg.astype('float32'),3)
                            )
                        else:
                            hdu = fits.PrimaryHDU(
                                outputimg.astype('float32')
                            )
                        del outputimg


                        hdu.header['PIXSCALE']=self.pixscale
                        hdu.header['EXPTIME']=exposure_time

                        hdu.header['OBSTYPE']='flat'
                        hdu.header['FILTER']=self.current_filter

                        # If the files are local calibrations, save them out to the local calibration directory
                        if not manually_requested_calibration:
                            g_dev['obs'].to_slow_process(200000000, ('localcalibration', raw_name00, hdu.data, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))


                        # Similarly to the above. This saves the RAW file to disk
                        if self.config['save_raw_to_disk']:
                            os.makedirs(
                                self.camera_path + g_dev["day"], exist_ok=True
                            )

                            os.makedirs(
                                raw_path, exist_ok=True
                            )
                            #g_dev['obs'].to_slow_process(1000,('raw', raw_path + raw_name00, hdu.data, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))
                            threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw', raw_path + raw_name00, hdu.data, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec,'no','deprecated')),)).start()


                        # For sites that have "save_to_alt_path" enabled, this routine
                        # Saves the raw and reduced fits files out to the provided directories
                        if self.config["save_to_alt_path"] == "yes":
                            self.alt_path = self.config[
                                "alt_path"
                            ]  +'/' + self.config['obs_id']+ '/' # NB NB this should come from config file, it is site dependent.

                            os.makedirs(
                                self.alt_path , exist_ok=True
                            )

                            os.makedirs(
                                self.alt_path + g_dev["day"], exist_ok=True
                            )

                            os.makedirs(
                               self.alt_path + g_dev["day"] + "/raw/" , exist_ok=True
                            )

                            # g_dev['obs'].to_slow_process(1000,('raw_alt_path', self.alt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header, \
                            #                                frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                            threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw_alt_path', self.alt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header, \
                                                           frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec,'no','deprecated')),)).start()


                                # if "hdusmalldata" in locals():
                            #     g_dev['obs'].to_slow_process(1000,('reduced_alt_path', selfalt_path + g_dev["day"] + "/reduced/" + red_name01, hdusmalldata, hdusmallheader, \
                            #                                        frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                        del hdu

                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        return copy.deepcopy(expresult)


                expresult["calc_sky"] = 0  # avg_ocn[7]
                expresult["temperature"] = 0  # avg_foc[2]
                expresult["gain"] = 0
                expresult["filter"] = self.current_filter
                expresult["error"] = False
                # filename same as raw_filename00 in post_exposure process

                if not frame_type[-4:] == "flat" and not frame_type in ["bias", "dark"]  and not a_dark_exposure and not focus_image and not frame_type=='pointing':
                    try:
                        im_type = "EX"
                        expresult["real_time_filename"] =  self.config["obs_id"]+ "-"+ self.alias + '_' + str(frame_type) + '_' + str(this_exposure_filter)+ "-"+ g_dev["day"]+ "-"+ next_seq+ "-"+ im_type+ "00.fits.fz"
                    except:
                        plog(traceback.format_exc())

                # plog("Exposure Complete")
                # g_dev["obs"].send_to_user("Exposure Complete")
                # self.running_an_exposure_set = False
                return copy.deepcopy(expresult)

            else:
                remaining = round(self.completion_time - time.time(), 1)

                # Need to have a time sleep to release the GIL to run the other threads
                if self.completion_time - time.time() > 0:
                    time.sleep(min(0.5, abs(self.completion_time - time.time() )))

                if remaining < -15:
                    #breakpoint()
                    if remaining > -16:
                        plog ("Camera overtime: " + str(remaining))


                    g_dev['obs'].request_scan_requests()
                    #g_dev['obs'].scan_requests()


                    # Check there hasn't been a cancel sent through
                    if g_dev["obs"].stop_all_activity:
                        plog ("stop_all_activity cancelling out of camera exposure")
                        Nsmartstack=1
                        sskcounter=2
                        expresult["error"] = True
                        expresult["stopped"] = True
                        g_dev["obs"].exposure_halted_indicator =False
                        self.currently_in_smartstack_loop=False
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        return expresult

                    if g_dev["obs"].exposure_halted_indicator:
                        expresult["error"] = True
                        expresult["stopped"] = True
                        g_dev["obs"].exposure_halted_indicator =False
                        plog ("Exposure Halted Indicator On. Cancelling Exposure.")
                        # self.running_an_exposure_set = False
                        # self.shutter_open=False
                        return expresult
                    # plog(
                    #     "Camera timed out; probably is no longer connected, resetting it now."
                    # )
                    # g_dev["obs"].send_to_user(
                    #     "Camera timed out; probably is no longer connected, resetting it now.",
                    #     p_level="INFO",
                    # )
                    # expresult = {"error": True}
                    # self.running_an_exposure_set = False
                    # plog ("Exposure Complete")
                    # g_dev["obs"].send_to_user("Exposure Complete")
                    # return expresult




def post_exposure_process(payload):

    expresult={}
    #A long tuple unpack of the payload
    (img, pier_side, is_osc, frame_type, reject_flat_by_known_gain, avg_mnt, avg_foc, avg_rot, \
     setpoint, tempccdtemp, ccd_humidity, ccd_pressure, darkslide_state, exposure_time, \
     this_exposure_filter, exposure_filter_offset, pane,opt, observer_user_name, hint, \
     azimuth_of_observation, altitude_of_observation, airmass_of_observation, pixscale, \
     smartstackid,sskcounter,Nsmartstack, longstackid, ra_at_time_of_exposure, \
     dec_at_time_of_exposure, manually_requested_calibration, object_name, object_specf, \
     ha_corr, dec_corr, focus_position, selfconfig, selfname, camera_known_gain, \
     camera_known_readnoise, start_time_of_observation, observer_user_id, selfcamera_path, \
     solve_it, next_seq, zoom_factor, useastrometrynet, substack, expected_endpoint_of_substack_exposure,substack_start_time,readout_estimate,readout_time, sub_stacker_midpoints) = payload
    post_exposure_process_timer=time.time()
    ix, iy = img.shape



    # Update readout time list
    readout_shelf = shelve.open(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + g_dev['cam'].alias + str(g_dev['obs'].name))
    try:
        readout_list=readout_shelf['readout_list']
    except:
        readout_list=[]

    readout_list.append(readout_estimate)

    too_long=True
    while too_long:
        if len(readout_list) > 100:
            readout_list.pop(0)
        else:
            too_long = False

    readout_shelf['readout_list'] = readout_list
    readout_shelf.close()

    image_saturation_level = g_dev['cam'].config["camera"][g_dev['cam'].name]["settings"]["saturate"]



    try:
        # THIS IS THE SECTION WHERE THE ORIGINAL FITS IMAGES ARE ROTATED
        # OR TRANSPOSED. THESE ARE ONLY USED TO ORIENTATE THE FITS
        # IF THERE IS A MAJOR PROBLEM with the original orientation
        # If you want to change the display on the UI, use the jpeg
        # alterations later on.
        if selfconfig["camera"][selfname]["settings"]["transpose_fits"]:
            hdu = fits.PrimaryHDU(
                img.transpose().astype('float32'))
        elif selfconfig["camera"][selfname]["settings"]["flipx_fits"]:
            hdu = fits.PrimaryHDU(
                np.fliplr(img.astype('float32'))
            )
        elif selfconfig["camera"][selfname]["settings"]["flipy_fits"]:
            hdu = fits.PrimaryHDU(
                np.flipud(img.astype('float32'))
            )
        elif selfconfig["camera"][selfname]["settings"]["rotate90_fits"]:
            hdu = fits.PrimaryHDU(
                np.rot90(img.astype('float32'))
            )
        elif selfconfig["camera"][selfname]["settings"]["rotate180_fits"]:
            hdu = fits.PrimaryHDU(
                np.rot90(img.astype('float32'),2)
            )
        elif selfconfig["camera"][selfname]["settings"]["rotate270_fits"]:
            hdu = fits.PrimaryHDU(
                np.rot90(img.astype('float32'),3)
            )
        else:
            hdu = fits.PrimaryHDU(
                img.astype('float32')
            )
        del img

        # assign the keyword values and comment of the keyword as a tuple to write both to header.

        hdu.header["BUNIT"] = ("adu", "Unit of array values")
        hdu.header["CCDXPIXE"] = (
            selfconfig["camera"][selfname]["settings"]["x_pixel"],
            "[um] Size of unbinned pixel, in X",
        )
        hdu.header["CCDYPIXE"] = (
            selfconfig["camera"][selfname]["settings"]["y_pixel"],
            "[um] Size of unbinned pixel, in Y",
        )
        hdu.header["XPIXSZ"] = (
            round(float(hdu.header["CCDXPIXE"]), 3),
            "[um] Size of binned pixel",
        )
        hdu.header["YPIXSZ"] = (
            round(float(hdu.header["CCDYPIXE"]), 3),
            "[um] Size of binned pixel",
        )
        hdu.header["XBINING"] = (1, "Pixel binning in x direction")
        hdu.header["YBINING"] = (1, "Pixel binning in y direction")

        hdu.header['CONFMODE'] = ('default',  'LCO Configuration Mode')
        hdu.header["DOCOSMIC"] = (
            selfconfig["camera"][selfname]["settings"]["do_cosmics"],
            "Header item to indicate whether to do cosmic ray removal",
        )

        hdu.header["CCDSTEMP"] = (
            round(setpoint, 2),     #WER fixed.
            "[C] CCD set temperature",
        )
        #hdu.header["COOLERON"] = self._cooler_on()
        hdu.header["CCDATEMP"] = (
            round(tempccdtemp, 2),
            "[C] CCD actual temperature",
        )
        hdu.header["CCDHUMID"] = round(ccd_humidity, 1)
        hdu.header["CCDPRESS"] = round(ccd_pressure, 1)
        hdu.header["OBSID"] = (
            selfconfig["obs_id"].replace("-", "").replace("_", "")
        )
        hdu.header["SITEID"] = (
            selfconfig["wema_name"].replace("-", "").replace("_", "")
        )
        hdu.header["TELID"] = selfconfig["telescope"]["telescope1"][
            "telescop"
        ][:4]
        hdu.header["TELESCOP"] = selfconfig["telescope"]["telescope1"][
            "telescop"
        ][:4]
        hdu.header["PTRTEL"] = selfconfig["telescope"]["telescope1"][
            "ptrtel"
        ]
        hdu.header["PROPID"] = "ptr-" + selfconfig["obs_id"] + "-001-0001"
        hdu.header["BLKUID"] = (
            "1234567890",
            "Just a placeholder right now. WER",
        )
        hdu.header["INSTRUME"] = (selfconfig["camera"][selfname]["name"], "Name of camera")
        hdu.header["CAMNAME"] = (selfconfig["camera"][selfname]["desc"], "Instrument used")
        hdu.header["DETECTOR"] = (
            selfconfig["camera"][selfname]["detector"],
            "Name of camera detector",
        )
        hdu.header["CAMMANUF"] = (
            selfconfig["camera"][selfname]["manufacturer"],
            "Name of camera manufacturer",
        )
        hdu.header["DARKSLID"] = (darkslide_state, "Darkslide state")
        hdu.header['SHUTTYPE'] = (selfconfig["camera"][selfname]["settings"]["shutter_type"],
                                  'Type of shutter')
        hdu.header["GAIN"] = (
            camera_known_gain,
            "[e-/ADU] Pixel gain",
        )
        hdu.header["ORIGGAIN"] = (
            camera_known_gain,
            "[e-/ADU] Original Pixel gain",
        )
        hdu.header["RDNOISE"] = (
            camera_known_readnoise,
            "[e-/pixel] Read noise",
        )
        hdu.header["OSCCAM"] = (is_osc, "Is OSC camera")
        hdu.header["OSCMONO"] = (False, "If OSC, is this a mono image or a bayer colour image.")

        hdu.header["FULLWELL"] = (
            selfconfig["camera"][selfname]["settings"][
                "fullwell_capacity"
            ],
            "Full well capacity",
        )

        is_cmos=selfconfig["camera"][selfname]["settings"]["is_cmos"]
        driver=selfconfig["camera"][selfname]["driver"]
        hdu.header["CMOSCAM"] = (is_cmos, "Is CMOS camera")

        if is_cmos and driver ==  "QHYCCD_Direct_Control":
            hdu.header["CMOSGAIN"] = (selfconfig["camera"][selfname][
                "settings"
            ]['direct_qhy_gain'], "CMOS Camera System Gain")


            hdu.header["CMOSOFFS"] = (selfconfig["camera"][selfname][
                "settings"
            ]['direct_qhy_offset'], "CMOS Camera System Offset")

            hdu.header["CAMUSBT"] = (selfconfig["camera"][selfname][
                "settings"
            ]['direct_qhy_usb_traffic'], "Camera USB traffic")
            hdu.header["READMODE"] = (selfconfig["camera"][selfname][
                "settings"
            ]['direct_qhy_readout_mode'], "QHY Readout Mode")



        hdu.header["READOUTE"]= (readout_estimate, "Readout time estimated from this exposure")
        hdu.header["READOUTU"] = (readout_time, "Readout time used for this exposure")
        hdu.header["OBSTYPE"] = (
            frame_type.upper(),
            "Observation type",
        )  # This report is fixed and it should vary...NEEDS FIXING!
        if frame_type.upper() == "SKY FLAT":
           frame_type =="SKYFLAT"
        hdu.header["IMAGETYP"] = (frame_type.upper(), "Observation type")

        hdu.header["TIMESYS"] = ("UTC", "Time system used")


        hdu.header["DAY-OBS"] = (
            g_dev["day"],
            "Date at start of observing night"
        )
        yesterday = datetime.datetime.now() - datetime.timedelta(1)
        hdu.header["L1PUBDAT"] = datetime.datetime.strftime(
            yesterday, "%Y-%m-%dT%H:%M:%S.%fZ"
        )  # IF THIS DOESN"T WORK, subtract the extra datetime ...

        # There is a significant difference between substack timing and "normal" exposure timing
        # Also it has impacts on the actual "exposure time" as well.... the exposure time is "longer" but has LESS effective exposure time

        if substack:

            #hdu.header["SUBSTK"] = (True, "Is this made from at-site sub exposures.")
            hdu.header["SUBEXPT"] = (expected_endpoint_of_substack_exposure - substack_start_time, "Time between start and end of subexposure set")

            # hdu.header.add_comment('Substacker Midpoints:')
            # hdu.header.add_comment(str(sub_stacker_midpoints))

            #hdu.header['SUBMIDTS'] = (str(sub_stacker_midpoints), "Midpoints of substack exposures")


            substack_midexposure=np.mean(np.array(sub_stacker_midpoints))

            # print ("substacker midpoints")
            # print (sub_stacker_midpoints)

            # print ("substacked midpoint")
            # print (substack_midexposure)


            hdu.header["DATE"] = (
                datetime.datetime.isoformat(
                    datetime.datetime.utcfromtimestamp(substack_start_time)
                ),
                "Start date and time of observation"
            )

            hdu.header["DATE-OBS"] = (
                datetime.datetime.isoformat(
                    datetime.datetime.utcfromtimestamp(substack_start_time)
                ),
                "Start date and time of observation"
            )

            hdu.header["MJD-OBS"] = (
                Time(substack_start_time, format="unix").mjd,
                "[UTC days] Modified Julian Date start date/time",
            )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
            hdu.header["JD-START"] = (
                Time(substack_start_time, format="unix").jd,
                "[UTC days] Julian Date at start of exposure",
            )


            hdu.header["MJD-MID"] = (
                Time(substack_midexposure, format="unix").mjd,
                "[UTC days] Modified Julian Date mid exposure date/time",
            )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
            hdu.header["JD-MID"] = (
                Time(substack_midexposure, format="unix").jd,
                "[UTC days] Julian Date at middle of exposure",
            )



            hdu.header["EXPTIME"] = (
                expected_endpoint_of_substack_exposure - substack_start_time,
                "[s] Actual exposure length",
            )  # This is the exposure in seconds specified by the user
            hdu.header["EFFEXPT"] = (
                exposure_time,
                "[s] Integrated exposure length",
            )
            hdu.header["EFFEXPN"] = (
                int(exposure_time / 10),
                "[s] Number of integrated exposures",
            )


            hdu.header[
                "EXPOSURE"
            ] = (
                expected_endpoint_of_substack_exposure - substack_start_time,
                "[s] Actual exposure length",
            )  # Ideally this needs to be calculated from actual times


        else:

            #hdu.header["SUBSTK"] = (False, "Is this made from at-site sub exposures.")

            hdu.header["DATE"] = (
                datetime.datetime.isoformat(
                    datetime.datetime.utcfromtimestamp(start_time_of_observation)
                ),
                "Start date and time of observation"
            )

            hdu.header["DATE-OBS"] = (
                datetime.datetime.isoformat(
                    datetime.datetime.utcfromtimestamp(start_time_of_observation)
                ),
                "Start date and time of observation"
            )

            hdu.header["MJD-OBS"] = (
                Time(start_time_of_observation, format="unix").mjd,
                "[UTC days] Modified Julian Date start date/time",

            )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
            hdu.header["JD-START"] = (
                Time(start_time_of_observation, format="unix").jd,
                "[UTC days] Julian Date at start of exposure")



            hdu.header["MJD-MID"] = (
                Time(start_time_of_observation + (0.5 * exposure_time), format="unix").mjd,
                "[UTC days] Modified Julian Date mid exposure date/time",
            )  # NB NB NB Needs to be fixed, mid-exposure dates as well.
            hdu.header["JD-MID"] = (
                Time(start_time_of_observation+ (0.5 * exposure_time), format="unix").jd,

                "[UTC days] Julian Date at middle of exposure",
            )


            hdu.header["EXPTIME"] = (
                exposure_time,
                "[s] Actual exposure length",
            )  # This is the exposure in seconds specified by the user
            hdu.header["EFFEXPT"] = (
                exposure_time,
                "[s] Integrated exposure length",
            )
            hdu.header["EFFEXPN"] = (
                1,
                "[s] Number of integrated exposures",
            )


            hdu.header[
                "EXPOSURE"
            ] = (
                exposure_time,
                "[s] Actual exposure length",
            )  # Ideally this needs to be calculated from actual times

        hdu.header["BUNIT"] = "adu"

        hdu.header["FILTER"] = (
            this_exposure_filter,
            "Filter type")
        if g_dev["fil"].null_filterwheel == False:
            hdu.header["FILTEROF"] = (exposure_filter_offset, "Filter offset")

            hdu.header["FILTRNUM"] = (
               "PTR_ADON_HA_0023",
               "An index into a DB",
               )
        else:
            hdu.header["FILTEROF"] = ("No Filter", "Filter offset")
            hdu.header["FILTRNUM"] = (
                "No Filter",
                "An index into a DB",
            )  # Get a number from the hardware or via Maxim.  NB NB why not cwl and BW instead, plus P

        # THESE ARE THE RELEVANT FITS HEADER KEYWORDS
        # FOR OSC MATCHING AT A LATER DATE.
        # THESE ARE SET TO DEFAULT VALUES FIRST AND
        # THINGS CHANGE LATER
        hdu.header["OSCMATCH"] = 'no'
        hdu.header['OSCSEP'] = 'no'
        # if g_dev["scr"] is not None and frame_type == "screenflat":
        #     hdu.header["SCREEN"] = (
        #         int(g_dev["scr"].bright_setting),
        #         "Screen brightness setting",
        #     )


        hdu.header["SATURATE"] = (
            float(image_saturation_level),
            "[ADU] Saturation level",
        )
        hdu.header["MAXLIN"] = (
            float(
                selfconfig["camera"][selfname]["settings"][
                    "max_linearity"
                ]
            ),
            "[ADU] Non-linearity level",
        )
        if pane is not None:
            hdu.header["MOSAIC"] = (True, "Is mosaic")
            hdu.header["PANE"] = pane

        hdu.header["FOCAL"] = (
            round(
                float(
                    selfconfig["telescope"]["telescope1"]["focal_length"]
                ),
                2,
            ),
            "[mm] Telescope focal length",
        )
        hdu.header["APR-DIA"] = (
            round(
                float(selfconfig["telescope"]["telescope1"]["aperture"]), 2
            ),
            "[mm] Telescope aperture",
        )
        hdu.header["APR-AREA"] = (
            round(
                float(
                    selfconfig["telescope"]["telescope1"][
                        "collecting_area"
                    ]
                ),
                1,
            ),
            "[mm^2] Telescope collecting area",
        )
        hdu.header["LATITUDE"] = (
            round(float(g_dev['evnt'].wema_config["latitude"]), 6),
            "[Deg N] Telescope Latitude",
        )
        hdu.header["LONGITUD"] = (
            round(float(g_dev['evnt'].wema_config["longitude"]), 6),
            "[Deg E] Telescope Longitude",
        )
        hdu.header["HEIGHT"] = (
            round(float(g_dev['evnt'].wema_config["elevation"]), 2),
            "[m] Altitude of Telescope above sea level",
        )
        hdu.header["MPC-CODE"] = (
            selfconfig["mpc_code"],
            "Site code",
        )  # This is made up for now.

        hdu.header["OBJECT"] =object_name
        hdu.header["OBJSPECF"] = object_specf


        if not any("OBJECT" in s for s in hdu.header.keys()):
            RAtemp = ra_at_time_of_exposure
            DECtemp = dec_at_time_of_exposure
            RAstring = f"{RAtemp:.1f}".replace(".", "h")
            DECstring = f"{DECtemp:.1f}".replace("-", "n").replace(".", "d")
            hdu.header["OBJECT"] = RAstring + "ra" + DECstring + "dec"
            hdu.header["OBJSPECF"] = "no"

        try:
            hdu.header["SID-TIME"] = (
                avg_mnt['sidereal_time'],
                "[deg] Sidereal time",
            )
            hdu.header["OBJCTRA"] = (
                float(avg_mnt['right_ascension']) * 15,
                "[deg] Object RA",
            )
            hdu.header["OBJCTDEC"] = (avg_mnt['declination'], "[deg] Object dec")
        except:
            plog("problem with the premount?")
            plog(traceback.format_exc())

        hdu.header["OBSERVER"] = (
            observer_user_name,
            "Observer name",
        )
        hdu.header["OBSNOTE"] = hint[0:54]  # Needs to be truncated.

        hdu.header["DITHER"] = (0, "[] Dither")  #This was intended to inform of a 5x5 pattern number
        hdu.header["OPERATOR"] = ("WER", "Site operator")

        hdu.header["ENCLIGHT"] = ("Off/White/Red/NIR", "Enclosure lights")
        hdu.header["ENCRLIGT"] = ("", "Enclosure red lights state")
        hdu.header["ENCWLIGT"] = ("", "Enclosure white lights state")


        hdu.header["MNT-SIDT"] = (
            avg_mnt["sidereal_time"],
            "[hrs] Mount sidereal time",
        )
        hdu.header["MNT-RA"] = (
            float(avg_mnt["right_ascension"]) * 15,
            "[deg] Mount RA",
        )
        ha = avg_mnt["sidereal_time"] - avg_mnt["right_ascension"]
        while ha >= 12:
            ha -= 24.0
        while ha < -12:
            ha += 24.0
        hdu.header["MNT-HA"] = (
            round(ha, 5),
            "[hrs] Average mount hour angle",
        )  # Note these are average mount observed values.

        hdu.header["MNT-DEC"] = (
            avg_mnt["declination"],
            "[deg] Average mount declination",
        )
        hdu.header["MNT-RAV"] = (
            avg_mnt["tracking_right_ascension_rate"],
            "[] Mount tracking RA rate",
        )
        hdu.header["MNT-DECV"] = (
            avg_mnt["tracking_declination_rate"],
            "[] Mount tracking dec rate",
        )
        hdu.header["AZIMUTH "] = (
            azimuth_of_observation,
            "[deg] Azimuth axis positions",
        )
        hdu.header["ALTITUDE"] = (
            altitude_of_observation,
            "[deg] Altitude axis position",
        )
        hdu.header["ZENITH"] = (90 - altitude_of_observation, "[deg] Zenith")
        hdu.header["AIRMASS"] = (
            airmass_of_observation,
            "Effective mean airmass",
        )
        #g_dev["airmass"] = float(airmass_of_observation)
        try:
            hdu.header["REFRACT"] = (
                round(g_dev["mnt"].refraction_rev, 3),
                "asec",
            )
        except:
            pass
        hdu.header["MNTRDSYS"] = (
            avg_mnt["coordinate_system"],
            "Mount coordinate system",
        )
        hdu.header["POINTINS"] = (avg_mnt["instrument"], "")
        hdu.header["MNT-PARK"] = (avg_mnt["is_parked"], "Mount is parked")
        hdu.header["MNT-SLEW"] = (avg_mnt["is_slewing"], "Mount is slewing")
        hdu.header["MNT-TRAK"] = (
            avg_mnt["is_tracking"],
            "Mount is tracking",
        )
        try:
            if pier_side == 0:
                hdu.header["PIERSIDE"] = ("Look West", "Pier on  East side")
                hdu.header["IMGFLIP"] = (True, "Is flipped")
                pier_string = "lw-"
            elif pier_side == 1:
                hdu.header["PIERSIDE"] = ("Look East", "Pier on West side")
                hdu.header["IMGFLIP"] = (False, "Is flipped")
                pier_string = "le-"
        except:
            hdu.header["PIERSIDE"] = "Undefined"
            pier_string = ""

        try:
            hdu.header["HACORR"] = (
                ha_corr,
                "[deg] Hour angle correction",
            )  # Should these be averaged?
            hdu.header["DECCORR"] = (
                dec_corr,
                "[deg] Declination correction",
            )
        except:
            pass
        hdu.header["OTA"] = "Main"
        hdu.header["SELECTEL"] = ("tel1", "Nominted OTA for pointing")
        try:
            hdu.header["ROTATOR"] = (
                selfconfig["rotator"]["rotator1"]["name"],
                "Rotator name",
            )
            hdu.header["ROTANGLE"] = (avg_rot[1], "[deg] Rotator angle")
            hdu.header["ROTMOVNG"] = (avg_rot[2], "Rotator is moving")
        except:
            pass

        try:
            hdu.header["FOCUS"] = (
                selfconfig["focuser"]["focuser1"]["name"],
                "Focuser name",
            )
            hdu.header["FOCUSPOS"] = (avg_foc[1], "[um] Focuser position")
            hdu.header["FOCUSTMP"] = (avg_foc[2], "[C] Focuser temperature")
            hdu.header["FOCUSMOV"] = (avg_foc[3], "Focuser is moving")
        except:
            plog("There is something fishy in the focuser routine")
        #try:
            #hdu.header["WXSTATE"] = (
            #    g_dev["ocn"].wx_is_ok,
            #    "Weather system state",
            #)
            #hdu.header["SKY-TEMP"] = (avg_ocn[1], "[C] Sky temperature")
            #hdu.header["AIR-TEMP"] = (
            #    avg_ocn[2],
            #    "[C] External temperature",
            #)
            #hdu.header["HUMIDITY"] = (avg_ocn[3], "[%] Percentage humidity")
            #hdu.header["DEWPOINT"] = (avg_ocn[4], "[C] Dew point")
            #hdu.header["WINDSPEE"] = (avg_ocn[5], "[km/h] Wind speed")
            #hdu.header["PRESSURE"] = (
            #    avg_ocn[6],
            #    "[mbar] Atmospheric pressure",
            #)
            #hdu.header["CALC-LUX"] = (
            #    avg_ocn[7],
            #    "[mag/arcsec^2] Expected sky brightness",
            #)
            #hdu.header["SKYMAG"] = (
            #    avg_ocn[8],
            #    "[mag/arcsec^2] Measured sky brightness",
            #)
        #except:
            #plog("have to not have ocn header items when no ocn")
         #   pass


        if pixscale == None:
            hdu.header["PIXSCALE"] = (
                'Unknown',
                "[arcsec/pixel] Nominal pixel scale on sky",
            )
        else:
            hdu.header["PIXSCALE"] = (
                float(pixscale),
                "[arcsec/pixel] Nominal pixel scale on sky",
            )

        hdu.header["DRZPIXSC"] = (selfconfig["camera"][selfname]["settings"]['drizzle_value_for_later_stacking'], 'Target pixel scale for drizzling')

        hdu.header["REQNUM"] = ("00000001", "Request number")
        hdu.header["ISMASTER"] = (False, "Is master image")
        current_camera_name = selfconfig["camera"][selfname]["name"]

        #next_seq = next_sequence(current_camera_name)
        hdu.header["FRAMENUM"] = (int(next_seq), "Running frame number")
        hdu.header["SMARTSTK"] = smartstackid # ID code for an individual smart stack group
        hdu.header["SSTKNUM"] = sskcounter
        hdu.header['SSTKLEN'] = Nsmartstack
        # hdu.header["LONGSTK"] = longstackid # Is this a member of a longer stack - to be replaced by
        #                                     #   longstack code soon

        hdu.header["SUBSTACK"] = substack
        hdu.header["PEDESTAL"] = (0.0, "This value has been added to the data")
        # hdu.header[
        #     "PATCH"
        # ] = central_median # A crude value for the central exposure
        hdu.header["ERRORVAL"] = 0

        hdu.header["USERNAME"] = observer_user_name
        hdu.header["USERID"] = (
            str(observer_user_id).replace("-", "").replace("|", "").replace('@','at')
        )


        im_type = "EX"  # or EN for engineering....
        f_ext = ""

        cal_name = (
            selfconfig["obs_id"]
            + "-"
            + current_camera_name
            + "-"
            + g_dev["day"]
            + "-"
            + next_seq
            + f_ext
            + "-"
            + im_type
            + "00.fits"
        )
        raw_name00 = (
            selfconfig["obs_id"]
            + "-"
            + current_camera_name + '_' + str(frame_type) + '_' + str(this_exposure_filter)
            + "-"
            + g_dev["day"]
            + "-"
            + next_seq
            + "-"
            + im_type
            + "00.fits"
        )

        if selfconfig['save_reduced_file_numberid_first']:
            red_name01 = (next_seq + "-" +selfconfig["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(hdu.header['FILTER']) + "-" +  str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")
        else:
            red_name01 = (selfconfig["obs_id"] + "-" + str(hdu.header['OBJECT']).replace(':','d').replace('@','at').replace('.','d').replace(' ','').replace('-','') +'-'+str(hdu.header['FILTER']) + "-" + next_seq+ "-" + str(exposure_time).replace('.','d') + "-"+ im_type+ "01.fits")

        red_name01_lcl = (
            red_name01[:-9]
            + pier_string + '-'
            + this_exposure_filter
            + red_name01[-9:]
        )
        if pane is not None:
            red_name01_lcl = (
                red_name01_lcl[:-9]
                + pier_string
                + "p"
                + str(abs(pane))
                + "-"
                + red_name01_lcl[-9:]
            )
        i768sq_name = (
            selfconfig["obs_id"]
            + "-"
            + current_camera_name
            + "-"
            + g_dev["day"]
            + "-"
            + next_seq
            + "-"
            + im_type
            + "10.fits"
        )
        jpeg_name = (
            selfconfig["obs_id"]
            + "-"
            + current_camera_name
            + "-"
            + g_dev["day"]
            + "-"
            + next_seq
            + "-"
            + im_type
            + "10.jpg"
        )
        text_name = (
            selfconfig["obs_id"]
            + "-"
            + current_camera_name
            + "-"
            + g_dev["day"]
            + "-"
            + next_seq
            + "-"
            + im_type
            + "00.txt"
        )
        im_path_r = selfcamera_path

        hdu.header["FILEPATH"] = str(im_path_r) + "to_AWS/"
        hdu.header["ORIGNAME"] = str(raw_name00 + ".fz")

        tempRAdeg = ra_at_time_of_exposure * 15
        tempDECdeg = dec_at_time_of_exposure
        tempointing = SkyCoord(tempRAdeg, tempDECdeg, unit='deg')
        tempointing=tempointing.to_string("hmsdms").split(' ')

        hdu.header["RA"] = (
            tempointing[0],
            "[hms] Telescope right ascension",
        )
        hdu.header["DEC"] = (
            tempointing[1],
            "[dms] Telescope declination",
        )
        hdu.header["ORIGRA"] = hdu.header["RA"]
        hdu.header["ORIGDEC"] = hdu.header["DEC"]
        hdu.header["RAhrs"] = (
            ra_at_time_of_exposure,
            "[hrs] Telescope right ascension",
        )
        hdu.header["RADEG"] = tempRAdeg
        hdu.header["DECDEG"] = tempDECdeg

        hdu.header["TARG-CHK"] = (
            (ra_at_time_of_exposure * 15)
            + dec_at_time_of_exposure,
            "[deg] Sum of RA and dec",
        )
        try:
            hdu.header["CATNAME"] = (object_name, "Catalog object name")
        except:
            hdu.header["CATNAME"] = ('Unknown', "Catalog object name")
        hdu.header["CAT-RA"] = (
            tempointing[0],
            "[hms] Catalog RA of object",
        )
        hdu.header["CAT-DEC"] = (
            tempointing[1],
            "[dms] Catalog Dec of object",
        )
        hdu.header["OFST-RA"] = (
            tempointing[0],
            "[hms] Catalog RA of object (for BANZAI only)",
        )
        hdu.header["OFST-DEC"] = (
            tempointing[1],
            "[dms] Catalog Dec of object",
        )


        hdu.header["TPT-RA"] = (
            tempointing[0],
            "[hms] Catalog RA of object (for BANZAI only",
        )
        hdu.header["TPT-DEC"] = (
            tempointing[1],
            "[dms] Catalog Dec of object",
        )

        hdu.header["RA-hms"] = tempointing[0]
        hdu.header["DEC-dms"] = tempointing[1]

        hdu.header["CTYPE1"] = 'RA---TAN'
        hdu.header["CTYPE2"] = 'DEC--TAN'
        try:
            hdu.header["CDELT1"] = pixscale / 3600
            hdu.header["CDELT2"] = pixscale / 3600
        except:
            hdu.header["CDELT1"] = 0.75 / 3600
            hdu.header["CDELT2"] = 0.75 / 3600

        hdu.header["CRVAL1"] = tempRAdeg
        hdu.header["CRVAL2"] = tempDECdeg
        hdu.header["CRPIX1"] = float(hdu.header["NAXIS1"])/2
        hdu.header["CRPIX2"] = float(hdu.header["NAXIS2"])/2

        try:  #  NB relocate this to Expose entry area.  Fill out except.  Might want to check on available space.
            os.makedirs(
                im_path_r + g_dev["day"] + "/to_AWS/", exist_ok=True
            )
            os.makedirs(im_path_r + g_dev["day"] + "/raw/", exist_ok=True)
            os.makedirs(im_path_r + g_dev["day"] + "/calib/", exist_ok=True)
            os.makedirs(
                im_path_r + g_dev["day"] + "/reduced/", exist_ok=True
            )
            im_path = im_path_r + g_dev["day"] + "/to_AWS/"
            raw_path = im_path_r + g_dev["day"] + "/raw/"
            cal_path = im_path_r + g_dev["day"] + "/calib/"
            red_path = im_path_r + g_dev["day"] + "/reduced/"

        except:
            pass

        paths = {
            "im_path": im_path,
            "raw_path": raw_path,
            "cal_path": cal_path,
            "red_path": red_path,
            "red_path_aux": None,
            "cal_name": cal_name,
            "raw_name00": raw_name00,
            "red_name01": red_name01,
            "red_name01_lcl": red_name01_lcl,
            "i768sq_name10": i768sq_name,
            "i768sq_name11": i768sq_name,
            "jpeg_name10": jpeg_name,
            "jpeg_name11": jpeg_name,
            "text_name00": text_name,
            "text_name10": text_name,
            "text_name11": text_name,
            "frame_type": frame_type,
        }

        if frame_type[-5:] in ["focus", "probe", "ental"]:
            focus_image = True
        else:
            focus_image = False

        hdusmalldata=copy.deepcopy(hdu.data)
        # Quick flash bias and dark frame
        selfnative_bin = selfconfig["camera"][selfname]["settings"]["native_bin"]

        broadband_ss_biasdark_exp_time = selfconfig['camera']['camera_1_1']['settings']['smart_stack_exposure_time']
        narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * selfconfig['camera']['camera_1_1']['settings']['smart_stack_exposure_NB_multiplier']
        dark_exp_time = selfconfig['camera']['camera_1_1']['settings']['dark_exposure']

        if not manually_requested_calibration and not substack:
            try:
                # If not a smartstack use a scaled masterdark
                timetakenquickdark=time.time()
                try:
                    if smartstackid == 'no':
                        # Initially debias the image
                        hdusmalldata = hdusmalldata - g_dev['cam'].biasFiles[str(1)]
                        # Sort out an intermediate dark
                        fraction_through_range=0
                        if exposure_time < 0.5:
                            hdusmalldata=hdusmalldata-(g_dev['cam'].darkFiles['halfsec_exposure_dark']*exposure_time)
                        elif exposure_time < 2.0:
                            fraction_through_range=(exposure_time-0.5)/(2.0-0.5)
                            tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['twosec_exposure_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['halfsec_exposure_dark'])
                            hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                            del tempmasterDark
                        elif exposure_time < 10.0:
                            fraction_through_range=(exposure_time-2)/(10.0-2.0)
                            tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['tensec_exposure_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['twosec_exposure_dark'])
                            hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                            del tempmasterDark
                        elif exposure_time < broadband_ss_biasdark_exp_time:
                            fraction_through_range=(exposure_time-10)/(broadband_ss_biasdark_exp_time-10.0)
                            tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['broadband_ss_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['tensec_exposure_dark'])
                            hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                            del tempmasterDark
                        elif exposure_time < narrowband_ss_biasdark_exp_time:
                            fraction_through_range=(exposure_time-broadband_ss_biasdark_exp_time)/(narrowband_ss_biasdark_exp_time-broadband_ss_biasdark_exp_time)
                            tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles['narrowband_ss_dark']) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['broadband_ss_dark'])
                            hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                            del tempmasterDark
                        elif dark_exp_time > narrowband_ss_biasdark_exp_time:
                            fraction_through_range=(exposure_time-narrowband_ss_biasdark_exp_time)/(dark_exp_time -narrowband_ss_biasdark_exp_time)
                            tempmasterDark=(fraction_through_range * g_dev['cam'].darkFiles[str(1)]) + ((1-fraction_through_range) * g_dev['cam'].darkFiles['narrowband_ss_dark'])
                            hdusmalldata=hdusmalldata-(tempmasterDark*exposure_time)
                            del tempmasterDark
                        else:
                            hdusmalldata=hdusmalldata-(g_dev['cam'].darkFiles['narrowband_ss_dark']*exposure_time)
                    elif exposure_time == broadband_ss_biasdark_exp_time:
                        hdusmalldata = hdusmalldata - (g_dev['cam'].darkFiles['broadband_ss_biasdark'])
                        #plog ("broadband biasdark success")
                    elif exposure_time == narrowband_ss_biasdark_exp_time:
                        hdusmalldata = hdusmalldata - (g_dev['cam'].darkFiles['narrowband_ss_biasdark'])
                        #plog ("narrowband biasdark success")

                    else:
                        plog ("DUNNO WHAT HAPPENED!")
                        hdusmalldata = hdusmalldata - g_dev['cam'].biasFiles[str(1)]
                        hdusmalldata = hdusmalldata - (g_dev['cam'].darkFiles[str(1)] * exposure_time)
                except:
                    try:
                        hdusmalldata = hdusmalldata - g_dev['cam'].biasFiles[str(1)]
                        hdusmalldata = hdusmalldata - (g_dev['cam'].darkFiles[str(1)] * exposure_time)
                    except:
                        plog ("Could not bias or dark file.")
                        #plog(traceback.format_exc())

                #plog ("time taken for flash reduction: " + str(time.time() - timetakenquickdark))
            except Exception as e:
                plog("debias/darking light frame failed: ", e)

            # Quick flat flat frame
            try:
                #plog ("FLATTERY")
                # if selfconfig['camera'][selfname]['settings']['hold_flats_in_memory']:
                #     hdusmalldata = np.divide(hdusmalldata, g_dev['cam'].flatFiles[g_dev['cam'].current_filter])
                # else:
                hdusmalldata = np.divide(hdusmalldata, np.load(g_dev['cam'].flatFiles[str(g_dev['cam'].current_filter + "_bin" + str(1))]))

            except Exception as e:
                plog("flatting light frame failed", e)
                #plog(traceback.format_exc())

            try:
                hdusmalldata[g_dev['cam'].bpmFiles[str(1)]] = np.nan

            except Exception as e:
                plog("Bad Pixel Masking light frame failed: ", e)



        # This saves the REDUCED file to disk
        # If this is for a smartstack, this happens immediately in the camera thread after we have a "reduced" file
        # So that the smartstack queue can start on it ASAP as smartstacks
        # are by far the longest task to undertake.
        # If it isn't a smartstack, it gets saved in the slow process queue.
        if "hdusmalldata" in locals():
            # Set up reduced header
            hdusmallheader=copy.deepcopy(hdu.header)
            if not manually_requested_calibration:
                #From the reduced data, crop around the edges of the
                #raw 1x1 image to get rid of overscan and crusty edge bits
                edge_crop=selfconfig["camera"][selfname]["settings"]['reduced_image_edge_crop']
                if edge_crop > 0:
                    hdusmalldata=hdusmalldata[edge_crop:-edge_crop,edge_crop:-edge_crop]

                    hdusmallheader['NAXIS1']=float(hdu.header['NAXIS1']) - (edge_crop * 2)
                    hdusmallheader['NAXIS2']=float(hdu.header['NAXIS2']) - (edge_crop * 2)
                    hdusmallheader['CRPIX1']=float(hdu.header['CRPIX1']) - (edge_crop * 2)
                    hdusmallheader['CRPIX2']=float(hdu.header['CRPIX2']) - (edge_crop * 2)

                # bin to native binning
                if selfnative_bin != 1 and (not pixscale == None):
                    reduced_hdusmalldata=(block_reduce(hdusmalldata,selfnative_bin))
                    reduced_hdusmallheader=copy.deepcopy(hdusmallheader)
                    reduced_hdusmallheader['XBINING']=selfnative_bin
                    reduced_hdusmallheader['YBINING']=selfnative_bin
                    reduced_hdusmallheader['PIXSCALE']=float(hdu.header['PIXSCALE']) * selfnative_bin
                    reduced_pixscale=float(hdu.header['PIXSCALE'])
                    reduced_hdusmallheader['NAXIS1']=float(hdu.header['NAXIS1']) / selfnative_bin
                    reduced_hdusmallheader['NAXIS2']=float(hdu.header['NAXIS2']) / selfnative_bin
                    reduced_hdusmallheader['CRPIX1']=float(hdu.header['CRPIX1']) / selfnative_bin
                    reduced_hdusmallheader['CRPIX2']=float(hdu.header['CRPIX2']) / selfnative_bin
                    reduced_hdusmallheader['CDELT1']=float(hdu.header['CDELT1']) * selfnative_bin
                    reduced_hdusmallheader['CDELT2']=float(hdu.header['CDELT2']) * selfnative_bin
                    reduced_hdusmallheader['CCDXPIXE']=float(hdu.header['CCDXPIXE']) * selfnative_bin
                    reduced_hdusmallheader['CCDYPIXE']=float(hdu.header['CCDYPIXE']) * selfnative_bin
                    reduced_hdusmallheader['XPIXSZ']=float(hdu.header['XPIXSZ']) * selfnative_bin
                    reduced_hdusmallheader['YPIXSZ']=float(hdu.header['YPIXSZ']) * selfnative_bin

                    reduced_hdusmallheader['SATURATE']=float(hdu.header['SATURATE']) * pow( selfnative_bin,2)
                    reduced_hdusmallheader['FULLWELL']=float(hdu.header['FULLWELL']) * pow( selfnative_bin,2)
                    reduced_hdusmallheader['MAXLIN']=float(hdu.header['MAXLIN']) * pow( selfnative_bin,2)

                    reduced_hdusmalldata=hdusmalldata+200.0
                    reduced_hdusmallheader['PEDESTAL']=200
                else:
                    reduced_hdusmalldata=copy.deepcopy(hdusmalldata)
                    reduced_hdusmallheader=copy.deepcopy(hdusmallheader)


                # Add a pedestal to the reduced data
                # This is important for a variety of reasons
                # Some functions don't work with arrays with negative values
                # 200 SHOULD be enough.
                hdusmalldata=hdusmalldata+200.0
                hdusmallheader['PEDESTAL']=200

                hdusmallheader["OBSID"] = (
                    selfconfig["obs_id"].replace("-", "").replace("_", "")
                )

                hdusmallheader["DAY-OBS"] = (
                    g_dev["day"],
                    "Date at start of observing night"
                )

                # Every Image gets SEP'd and gets it's catalogue sent up pronto ahead of the big fits
                # Focus images use it for focus, Normal images also report their focus.
                # IMMEDIATELY SEND TO SEP QUEUE
                # NEEDS to go up as fast as possible ahead of smartstacks to faciliate image matching.
                #g_dev['obs'].sep_processing=True
                #breakpoint()
                #print ("to_sep exposure: " + str(exposure_time))
                g_dev['obs'].to_sep((hdusmalldata, pixscale, float(hdu.header["RDNOISE"]), avg_foc[1], focus_image, im_path, text_name, hdusmallheader, cal_path, cal_name, frame_type, focus_position, selfnative_bin, exposure_time))


                if smartstackid != 'no':
                    try:
                        np.save(red_path + red_name01.replace('.fits','.npy'), hdusmalldata)
                        hdusstack=fits.PrimaryHDU()
                        hdusstack.header=hdusmallheader
                        hdusstack.header["NAXIS1"] = hdusmalldata.shape[0]
                        hdusstack.header["NAXIS2"] = hdusmalldata.shape[1]
                        hdusstack.writeto(red_path + red_name01.replace('.fits','.head'), overwrite=True, output_verify='silentfix')
                        saver = 1
                    except Exception as e:
                        plog("Failed to write raw file: ", e)

                if smartstackid == 'no':
                    if selfconfig['keep_reduced_on_disk']:

                        # if selfconfig["save_to_alt_path"] == "yes":
                        #     selfalt_path = selfconfig[
                        #         "alt_path"
                        #     ]  +'/' + selfconfig['obs_id']+ '/' # NB NB this should come from config file, it is site dependent.

                        #     if "reduced_hdusmalldata" in locals():


                        #         g_dev['obs'].to_slow_process(1000,('reduced_alt_path', selfalt_path + g_dev["day"] + "/reduced/" + red_name01, reduced_hdusmalldata, reduced_hdusmallheader, \
                        #                                            frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                        if selfconfig["save_to_alt_path"] == "yes":
                            selfalt_path = selfconfig[
                                "alt_path"
                            ]  +'/' + selfconfig['obs_id']+ '/' # NB NB this should come from config file, it is site dependent.
                        else:
                            selfalt_path = 'no'


                        # g_dev['obs'].to_slow_process(1000,('reduced', red_path + red_name01, reduced_hdusmalldata, reduced_hdusmallheader, \
                        #                        frame_type, ra_at_time_of_exposure,dec_at_time_of_exposure,selfalt_path))

                        slow_process=('reduced', red_path + red_name01, reduced_hdusmalldata, reduced_hdusmallheader, \
                                               frame_type, ra_at_time_of_exposure,dec_at_time_of_exposure,selfalt_path)

                        # Make  sure the alt paths exist
                        if g_dev['obs'].config["save_to_alt_path"] == "yes":
                            os.makedirs(
                                g_dev['obs'].alt_path + g_dev["day"], exist_ok=True
                            )
                            os.makedirs(
                                g_dev['obs'].alt_path + g_dev["day"] + "/raw/", exist_ok=True
                            )
                            os.makedirs(
                                g_dev['obs'].alt_path + g_dev["day"] + "/reduced/", exist_ok=True
                            )
                            os.makedirs(
                                g_dev['obs'].alt_path + g_dev["day"] + "/calib/", exist_ok=True)



                            altpath=copy.deepcopy(g_dev['obs'].alt_path)
                        else:
                            altpath='no'


                        picklepayload=(reduced_hdusmallheader,copy.deepcopy(g_dev['obs'].config),g_dev['cam'].name, slow_process, altpath)

                        #if True :
                        picklefilename='testred'+str(time.time()).replace('.','')
                        #pickle.dump(picklepayload, open('subprocesses/testfz'+str(time.time()).replace('.',''),'wb'))
                        pickle.dump(picklepayload, open(g_dev['obs'].local_calibration_path + 'smartstacks/'+picklefilename,'wb'))
                        #breakpoint()


                        # if sskcounter >0:
                        #breakpoint()

                        #print (picklefilename)

                        subprocess.Popen(['python','local_reduce_file_subprocess.py',picklefilename],cwd=g_dev['obs'].local_calibration_path + 'smartstacks',stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)


                        # if g_dev['obs'].config["save_to_alt_path"] == "yes":

                        #     altfolder = g_dev['obs'].config['temporary_local_alt_archive_to_hold_files_while_copying']
                        #     if not os.path.exists(g_dev['obs'].config['temporary_local_alt_archive_to_hold_files_while_copying']):
                        #         os.makedirs(g_dev['obs'].config['temporary_local_alt_archive_to_hold_files_while_copying'] )

                        #     # #breakpoint()
                        #     # hdureduced.writeto( altfolder +'/' + slow_process[1].split('/')[-1].replace('EX00','EX00-'+temphduheader['OBSTYPE']), overwrite=True, output_verify='silentfix'
                        #     #)  # Save full raw file locally
                        #     g_dev['obs'].altarchive_queue.put((copy.deepcopy(altfolder +'/' + slow_process[1].split('/')[-1].replace('EX00','EX00-'+reduced_hdusmallheader['OBSTYPE'])),copy.deepcopy(slow_process[1]),time.time()), block=False)



                # This puts the file into the smartstack queue
                # And gets it underway ASAP.

                if frame_type.lower() in ['fivepercent_exposure_dark','tenpercent_exposure_dark', 'quartersec_exposure_dark', 'halfsec_exposure_dark','threequartersec_exposure_dark','onesec_exposure_dark', 'oneandahalfsec_exposure_dark', 'twosec_exposure_dark', 'fivesec_exposure_dark', 'tensec_exposure_dark', 'fifteensec_exposure_dark', 'twentysec_exposure_dark', 'broadband_ss_biasdark', 'narrowband_ss_biasdark']:
                    a_dark_exposure=True
                else:
                    a_dark_exposure=False

                if ( not frame_type.lower() in [
                    "bias",
                    "dark",
                    "flat",
                    "solar",
                    "lunar",
                    "skyflat",
                    "screen",
                    "spectrum",
                    "auto_focus",
                    "focus",
                    "pointing"
                ]) and smartstackid != 'no' and not a_dark_exposure :
                    g_dev['obs'].to_smartstack((paths, pixscale, smartstackid, sskcounter, Nsmartstack, pier_side, zoom_factor))
                else:
                    if not selfconfig['keep_reduced_on_disk']:
                        try:
                            os.remove(red_path + red_name01)
                        except:
                            pass

            # Send data off to process jpeg
            # This is for a non-focus jpeg
            g_dev['obs'].to_mainjpeg((hdusmalldata, smartstackid, paths, pier_side, zoom_factor))



            if solve_it == True or (not manually_requested_calibration or ((Nsmartstack == sskcounter+1) and Nsmartstack > 1)\
                                       or g_dev['obs'].images_since_last_solve > g_dev['obs'].config["solve_nth_image"] or (datetime.datetime.utcnow() - g_dev['obs'].last_solve_time)  > datetime.timedelta(minutes=g_dev['obs'].config["solve_timer"])):

                cal_name = (
                    cal_name[:-9] + "F012" + cal_name[-7:]
                )

                # Check this is not an image in a smartstack set.
                # No shifts in pointing are wanted in a smartstack set!
                image_during_smartstack=False
                if Nsmartstack > 1 and not ((Nsmartstack == sskcounter+1) or sskcounter ==0):
                    image_during_smartstack=True
                if exposure_time < 1.0:
                    plog ("Not doing Platesolve for sub-second exposures.")
                else:
                    if solve_it == True or (not image_during_smartstack and not g_dev['seq'].currently_mosaicing and not g_dev['obs'].pointing_correction_requested_by_platesolve_thread and g_dev['obs'].platesolve_queue.empty() and not g_dev['obs'].platesolve_is_processing):

                        # Make sure any dither or return nudge has finished before platesolution
                        if sskcounter == 0 and Nsmartstack > 1:
                            firstframesmartstack = True
                        else:
                            firstframesmartstack = False


                        g_dev['obs'].to_platesolve((hdusmalldata, hdusmallheader, cal_path, cal_name, frame_type, time.time(), pixscale, ra_at_time_of_exposure,dec_at_time_of_exposure, firstframesmartstack, useastrometrynet))
                        # If it is the last of a set of smartstacks, we actually want to
                        # wait for the platesolve and nudge before starting the next smartstack.

            # Now that the jpeg, sep and platesolve has been sent up pronto,
            # We turn back to getting the bigger raw, reduced and fz files dealt with
            if not ( frame_type.lower() in [
                "bias",
                "dark"
                "flat",
                "focus",
                "skyflat",
                "pointing"
                ]) and not a_dark_exposure:
                #g_dev['obs'].to_slow_process(5,('fz_and_send', raw_path + raw_name00 + ".fz", copy.deepcopy(hdu.data), copy.deepcopy(hdu.header), frame_type, ra_at_time_of_exposure,dec_at_time_of_exposure))

                #slow_process=('fz_and_send', raw_path + raw_name00 + ".fz", copy.deepcopy(hdu.data), copy.deepcopy(hdu.header), frame_type, ra_at_time_of_exposure,dec_at_time_of_exposure)
                picklepayload=(copy.deepcopy(hdu.header),copy.deepcopy(g_dev['obs'].config),g_dev['cam'].name, ('fz_and_send', raw_path + raw_name00 + ".fz", copy.deepcopy(hdu.data), copy.deepcopy(hdu.header), frame_type, ra_at_time_of_exposure,dec_at_time_of_exposure))

                #if True :
                picklefilename='testlocalred'+str(time.time()).replace('.','')
                #pickle.dump(picklepayload, open('subprocesses/testfz'+str(time.time()).replace('.',''),'wb'))
                pickle.dump(picklepayload, open(g_dev['obs'].local_calibration_path + 'smartstacks/'+picklefilename,'wb'))
                #breakpoint()


                # if sskcounter >0:
                #breakpoint()

                # print (picklefilename)

                # print(slow_process[1])

                subprocess.Popen(['python','fz_archive_file.py',picklefilename],cwd=g_dev['obs'].local_calibration_path + 'smartstacks',stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)


                #goog_subprocess.communicate()
                #breakpoint()

                # try:
                #     pickle.dump(picklepayload, smartstack_subprocess.stdin)
                # except:
                #     plog ("Problem in the smartstack pickle dump")
                #     plog(traceback.format_exc())



                # # Create the fz file ready for PTR Archive
                # # Note that even though the raw file is int16,
                # # The compression and a few pieces of software require float32
                # # BUT it actually compresses to the same size either way
                # hdu.header["BZERO"] = 0  # Make sure there is no integer scaling left over
                # hdu.header["BSCALE"] = 1  # Make sure there is no integer scaling left over
                # if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:


                #     pipefolder = g_dev['obs'].config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(hdu.header['DAY-OBS']) +'/'+ str(hdu.header['INSTRUME'])
                    # if not os.path.exists(self.config['temporary_local_pipe_archive_to_hold_files_while_copying']+'/'+ str(hdu.header['DAY-OBS'])):
                    #     os.makedirs(self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(hdu.header['DAY-OBS']))

                    # if not os.path.exists(self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(hdu.header['DAY-OBS']) +'/'+ str(hdu.header['INSTRUME'])):
                    #     os.makedirs(self.config['temporary_local_pipe_archive_to_hold_files_while_copying'] +'/'+ str(hdu.header['DAY-OBS']) +'/'+ str(hdu.header['INSTRUME']))



                if not g_dev['obs'].config["camera"][g_dev['cam'].name]["settings"]["is_osc"]:


                    # # This routine saves the file ready for uploading to AWS
                    # # It usually works perfectly 99.9999% of the time except
                    # # when there is an astropy cache error. It is likely that
                    # # the cache will need to be cleared when it fails, but
                    # # I am still waiting for it to fail again (rare)
                    # saver = 0
                    # saverretries = 0
                    # while saver == 0 and saverretries < 10:
                    #     try:
                    #         if self.config['ingest_raws_directly_to_archive']:
                    #             hdufz = fits.CompImageHDU(
                    #                 np.array(slow_process[2], dtype=np.float32), hdu.header
                    #             )
                    #             hdufz.writeto(
                    #                 slow_process[1], overwrite=True
                    #             )  # Save full fz file locally
                    #             try:
                    #                 hdufz.close()
                    #             except:
                    #                 pass
                    #             del hdufz  # remove file from memory now that we are doing with it

                    #         if self.config['save_raws_to_pipe_folder_for_nightly_processing']:

                    #             hdu = fits.PrimaryHDU(np.array(slow_process[2], dtype=np.float32), hdu.header)


                    #             #plog ("gonna pipe folder")
                    #             #plog (pipefolder + '/' + str(hdu.header['ORIGNAME']))
                    #             hdu.writeto(
                    #                 pipefolder + '/' + str(hdu.header['ORIGNAME']).replace('.fits.fz','.fits'), overwrite=True
                    #             )
                    #             try:
                    #                 hdu.close()
                    #             except:
                    #                 pass
                    #             del hdu  # remove file from memory now that we are doing with it

                                #(filename,dayobs,instrume) = fileinfo
                    # if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:

                    #     g_dev['obs'].pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(hdu.header['ORIGNAME']).replace('.fits.fz','.fits')),copy.deepcopy(hdu.header['DAY-OBS']),copy.deepcopy(hdu.header['INSTRUME']),time.time()), block=False)
                                #hdufz.writeto(
                                #    slow_process[1], overwrite=True
                                #)  # Save full fz file locally
                        #     saver = 1
                        # except Exception as e:
                        #     plog("Failed to write raw fz file: ", e)
                        #     if "requested" in e and "written" in e:
                        #         plog(check_download_cache())
                        #     plog(traceback.format_exc())
                        #     time.sleep(10)
                        #     saverretries = saverretries + 1


                    # Send this file up to ptrarchive
                    if g_dev['obs'].config['send_files_at_end_of_night'] == 'no' and g_dev['obs'].config['ingest_raws_directly_to_archive']:

                        #print ("INGESTERING " + raw_name00)
                        g_dev['obs'].enqueue_for_PTRarchive(
                            26000000, '', raw_path + raw_name00 +'.fz'
                        )

                else:  # Is an OSC

                    if g_dev['obs'].config["camera"][g_dev['cam'].name]["settings"]["osc_bayer"] == 'RGGB':

                        # newhdured = slow_process[2][::2, ::2]
                        # GTRonly = slow_process[2][::2, 1::2]
                        # GBLonly = slow_process[2][1::2, ::2]
                        # newhdublue = slow_process[2][1::2, 1::2]
                        # clearV = (block_reduce(slow_process[2],2))

                        # oscmatchcode = (datetime.datetime.now().strftime("%d%m%y%H%M%S"))

                        #hdu.header["OSCMATCH"] = oscmatchcode
                        #hdu.header['OSCSEP'] = 'yes'
                        # hdu.header['NAXIS1'] = float(hdu.header['NAXIS1'])/2
                        # hdu.header['NAXIS2'] = float(hdu.header['NAXIS2'])/2
                        # hdu.header['CRPIX1'] = float(hdu.header['CRPIX1'])/2
                        # hdu.header['CRPIX2'] = float(hdu.header['CRPIX2'])/2
                        try:
                            hdu.header['PIXSCALE'] = float(hdu.header['PIXSCALE'])*2
                        except:
                            pass
                        hdu.header['CDELT1'] = float(hdu.header['CDELT1'])*2
                        hdu.header['CDELT2'] = float(hdu.header['CDELT2'])*2
                        tempfilter = hdu.header['FILTER']
                        tempfilename = raw_path + raw_name00



                        # Save and send R1
                        hdu.header['FILTER'] = tempfilter + '_R1'
                        hdu.header['ORIGNAME'] = hdu.header['ORIGNAME'].replace('-EX', 'R1-EX')



                        if g_dev['obs'].config['send_files_at_end_of_night'] == 'no' and g_dev['obs'].config['ingest_raws_directly_to_archive']:
                            # hdufz = fits.CompImageHDU(
                            #     np.array(newhdured, dtype=np.float32), hdu.header
                            # )
                            # hdufz.writeto(
                            #     tempfilename.replace('-EX', 'R1-EX'), overwrite=True#, output_verify='silentfix'
                            # )  # Save full fz file locally
                            g_dev['obs'].enqueue_for_PTRarchive(
                                26000000, '', tempfilename.replace('-EX', 'R1-EX') + '.fz'
                            )

                        # if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                        #     # hdu = fits.PrimaryHDU(np.array(newhdured, dtype=np.float32), hdu.header)
                        #     hdu.header['ORIGNAME']=hdu.header['ORIGNAME'].replace('.fits.fz','.fits')
                        #     # hdu.writeto(
                        #     #     pipefolder + '/' + str(hdu.header['ORIGNAME']), overwrite=True
                        #     # )
                        #     g_dev['obs'].pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(hdu.header['ORIGNAME'])),copy.deepcopy(hdu.header['DAY-OBS']),copy.deepcopy(hdu.header['INSTRUME']),time.time()), block=False)

                        # del newhdured

                        # Save and send G1
                        hdu.header['FILTER'] = tempfilter + '_G1'
                        hdu.header['ORIGNAME'] = hdu.header['ORIGNAME'].replace('R1-EX', 'G1-EX')



                        if g_dev['obs'].config['send_files_at_end_of_night'] == 'no' and g_dev['obs'].config['ingest_raws_directly_to_archive']:
                            # hdufz = fits.CompImageHDU(
                            #     np.array(GTRonly, dtype=np.float32), hdu.header
                            # )
                            # hdufz.writeto(
                            #     tempfilename.replace('-EX', 'G1-EX'), overwrite=True#, output_verify='silentfix'
                            # )  # Save full fz file locally
                            g_dev['obs'].enqueue_for_PTRarchive(
                                26000000, '', tempfilename.replace('-EX', 'G1-EX')+ '.fz'
                            )
                        # if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                        #     # hdu = fits.PrimaryHDU(np.array(GTRonly, dtype=np.float32), hdu.header)
                        #     hdu.header['ORIGNAME']=hdu.header['ORIGNAME'].replace('.fits.fz','.fits')

                        #     # hdu.writeto(
                        #     #     pipefolder + '/' + str(hdu.header['ORIGNAME']), overwrite=True
                        #     # )
                        #     g_dev['obs'].pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(hdu.header['ORIGNAME'])),copy.deepcopy(hdu.header['DAY-OBS']),copy.deepcopy(hdu.header['INSTRUME']),time.time()), block=False)
                        # # del GTRonly

                        # Save and send G2
                        hdu.header['FILTER'] = tempfilter + '_G2'
                        hdu.header['ORIGNAME'] = hdu.header['ORIGNAME'].replace('G1-EX', 'G2-EX')




                        if g_dev['obs'].config['send_files_at_end_of_night'] == 'no' and g_dev['obs'].config['ingest_raws_directly_to_archive']:
                            # hdufz = fits.CompImageHDU(
                            #     np.array(GBLonly, dtype=np.float32), hdu.header
                            # )
                            # hdufz.writeto(
                            #     tempfilename.replace('-EX', 'G2-EX'), overwrite=True#, output_verify='silentfix'
                            # )  # Save full fz file locally
                            g_dev['obs'].enqueue_for_PTRarchive(
                                26000000, '', tempfilename.replace('-EX', 'G2-EX')+ '.fz'
                            )
                        # if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                        #     # hdu = fits.PrimaryHDU(np.array(GBLonly, dtype=np.float32), hdu.header)
                        #     hdu.header['ORIGNAME']=hdu.header['ORIGNAME'].replace('.fits.fz','.fits')

                        #     # hdu.writeto(
                        #     #     pipefolder + '/' + str(hdu.header['ORIGNAME']), overwrite=True
                        #     # )
                        #     g_dev['obs'].pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(hdu.header['ORIGNAME'])),copy.deepcopy(hdu.header['DAY-OBS']),copy.deepcopy(hdu.header['INSTRUME']),time.time()), block=False)

                        # del GBLonly

                        # Save and send B1
                        hdu.header['FILTER'] = tempfilter + '_B1'
                        hdu.header['ORIGNAME'] = hdu.header['ORIGNAME'].replace('G2-EX', 'B1-EX')




                        if g_dev['obs'].config['send_files_at_end_of_night'] == 'no' and g_dev['obs'].config['ingest_raws_directly_to_archive']:
                            # hdufz = fits.CompImageHDU(
                            #     np.array(newhdublue, dtype=np.float32), hdu.header
                            # )
                            # hdufz.writeto(
                            #     tempfilename.replace('-EX', 'B1-EX'), overwrite=True#, output_verify='silentfix'
                            # )  # Save full fz file locally
                            g_dev['obs'].enqueue_for_PTRarchive(
                                26000000, '', tempfilename.replace('-EX', 'B1-EX')+ '.fz'
                            )
                        # if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                        #     # hdu = fits.PrimaryHDU(np.array(newhdublue, dtype=np.float32), hdu.header)
                        #     hdu.header['ORIGNAME']=hdu.header['ORIGNAME'].replace('.fits.fz','.fits')

                        #     # hdu.writeto(
                        #     #     pipefolder + '/' + str(hdu.header['ORIGNAME']), overwrite=True
                        #     # )
                        #     g_dev['obs'].pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(hdu.header['ORIGNAME'])),copy.deepcopy(hdu.header['DAY-OBS']),copy.deepcopy(hdu.header['INSTRUME']),time.time()), block=False)
                        # # del newhdublue

                        # Save and send clearV
                        hdu.header['FILTER'] = tempfilter + '_clearV'
                        hdu.header['ORIGNAME'] = hdu.header['ORIGNAME'].replace('B1-EX', 'CV-EX')

                        # hdu.header['SATURATE']=float(hdu.header['SATURATE']) * 4
                        # hdu.header['FULLWELL']=float(hdu.header['FULLWELL']) * 4
                        # hdu.header['MAXLIN']=float(hdu.header['MAXLIN']) * 4





                        if g_dev['obs'].config['send_files_at_end_of_night'] == 'no' and g_dev['obs'].config['ingest_raws_directly_to_archive']:
                            # hdufz = fits.CompImageHDU(
                            #     np.array(clearV, dtype=np.float32), hdu.header
                            # )
                            # hdufz.writeto(
                            #     tempfilename.replace('-EX', 'CV-EX'), overwrite=True#, output_verify='silentfix'
                            # )
                            g_dev['obs'].enqueue_for_PTRarchive(
                                26000000, '', tempfilename.replace('-EX', 'CV-EX')+ '.fz'
                            )
                        # if g_dev['obs'].config['save_raws_to_pipe_folder_for_nightly_processing']:
                        #     # hdu = fits.PrimaryHDU(np.array(clearV, dtype=np.float32), hdu.header)
                        #     # hdu.header['ORIGNAME']=hdu.header['ORIGNAME'].replace('.fits.fz','.fits')

                        #     # hdu.writeto(
                        #     #     pipefolder + '/' + str(hdu.header['ORIGNAME']), overwrite=True
                        #     # )
                        #     g_dev['obs'].pipearchive_queue.put((copy.deepcopy(pipefolder + '/' + str(hdu.header['ORIGNAME'])),copy.deepcopy(hdu.header['DAY-OBS']),copy.deepcopy(hdu.header['INSTRUME']),time.time()), block=False)
                        # # del clearV


                    else:
                        plog("this bayer grid not implemented yet")



            # Similarly to the above. This saves the RAW file to disk
            # it works 99.9999% of the time.
            if selfconfig['save_raw_to_disk']:

                #breakpoint()
                # print ("first")
                # try:
                # os.makedirs(
                #     self.camera_path + g_dev["day"], exist_ok=True
                # )

                os.makedirs(
                    raw_path, exist_ok=True
                )
                threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw', raw_path + raw_name00, hdu.data, hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec,'no','thisisdeprecated')),)).start()

                # except:
                #     breakpoint()

                #g_dev['obs'].to_slow_process(1000,)

                if selfconfig["save_to_alt_path"] == "yes":
                    selfalt_path = selfconfig[
                        "alt_path"
                    ]  +'/' + selfconfig['obs_id']+ '/' # NB NB this should come from config file, it is site dependent.
                    # print ("second")
                    # try:

                    os.makedirs(
                        selfalt_path , exist_ok=True
                    )

                    os.makedirs(
                        selfalt_path + g_dev["day"], exist_ok=True
                    )

                    os.makedirs(
                       selfalt_path + g_dev["day"] + "/raw/" , exist_ok=True
                    )
                    threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw_alt_path', selfalt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header, \
                                                       frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec,'no','deprecated')),)).start()
                    # except:
                    #     breakpoint()

                    # g_dev['obs'].to_slow_process(1000,('raw_alt_path', selfalt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header, \
                    #                                frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))


            # For sites that have "save_to_alt_path" enabled, this routine
            # Saves the raw and reduced fits files out to the provided directories



            # remove file from memory
            try:
                hdu.close()
            except:
                pass
            del hdu  # remove file from memory now that we are doing with it

            if "hdusmalldata" in locals():
                try:
                    hdusmalldata.close()
                except:
                    pass
                del hdusmalldata  # remove file from memory now that we are doing with it
            if "reduced_hdusmalldata" in locals():
                try:
                    del reduced_hdusmalldata
                    del reduced_hdusmallheader
                except:
                    pass

            #print ("Post-exposure process length: " + str(time.time() -post_exposure_process_timer))
        #del img

    except:
        plog(traceback.format_exc())

def wait_for_slew():
    """
    A function called when the code needs to wait for the telescope to stop slewing before undertaking a task.
    """
    if not g_dev['obs'].mountless_operation:
        try:
            if not g_dev['mnt'].rapid_park_indicator:
                movement_reporting_timer=time.time()
                while g_dev['mnt'].return_slewing(): #or g_dev['enc'].status['dome_slewing']:   #Filter is moving??
                #while g_dev['mnt'].mount.Slewing():
                    #g_dev['mnt'].currently_slewing= True
                    if time.time() - movement_reporting_timer > 2.0:
                        plog( 'm>')
                        movement_reporting_timer=time.time()
                    if not g_dev['obs'].currently_updating_status and g_dev['obs'].update_status_queue.empty():
                        g_dev['mnt'].get_mount_coordinates()
                        #g_dev['obs'].request_update_status(mount_only=True, dont_wait=True)
                        g_dev['obs'].update_status(mount_only=True, dont_wait=True)
                #g_dev['mnt'].currently_slewing= False

        except Exception as e:
            plog("Motion check faulted.")
            plog(traceback.format_exc())
            if 'pywintypes.com_error' in str(e):
                plog ("Mount disconnected. Recovering.....")
                time.sleep(5)
                g_dev['mnt'].reboot_mount()
            else:
                pass
        return



