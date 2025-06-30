"""
camera.py  camera.py  camera.py  camera.py  camera.py  camera.py  camera.py

Created on Tue Apr 20 22:19:25 2021

@author: obs, wer, dhunt

"""

from PIL import Image  # , ImageDraw
from astropy.coordinates import SkyCoord , AltAz, get_sun
#from scipy.stats import binned_statistic
from ctypes import *
from ptr_utility import plog
from global_yard import g_dev
from devices.darkslide import Darkslide
#import matplotlib
#matplotlib.use('Agg')
import matplotlib.style as mplstyle
import matplotlib as mpl
import subprocess
import warnings
# from scipy.ndimage import gaussian_filter
from astropy.utils.exceptions import AstropyUserWarning
# from astropy.convolution import interpolate_replace_nans, Gaussian2DKernel
from astropy.table import Table
from astropy.nddata import block_reduce
from astropy.modeling import models, fitting
from astropy.nddata import Cutout2D
from astropy import units as u
#from astropy.coordinates import SkyCoord
# from astroscrappy import detect_cosmics
from photutils.detection import DAOStarFinder
from astropy.stats import mad_std
import threading
import sep
import math
from astropy.stats import sigma_clip
from scipy.spatial import cKDTree
import pickle
import win32com.client
import bottleneck as bn
import numpy as np
import glob
#from astropy.nddata import block_reduce
from astropy.time import Time
from astropy.io import fits
from datetime import datetime, date, timedelta, timezone
import os
import shelve
import time
import traceback
import ephem
import copy
import json
import random
from astropy import log
import zwoasi as asi
from scipy import ndimage
from multiprocessing import Pool
import multiprocessing
log.setLevel('ERROR')
# We only use Observatory in type hints, so use a forward reference to prevent circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from obs import Observatory
# import matplotlib.pyplot as plt
# from matplotlib.patches import Circle
# from matplotlib.patches import Ellipse
# from matplotlib.collections import PatchCollection
from skimage.filters import threshold_local
from skimage.morphology import remove_small_objects
from skimage.measure import label, regionprops, regionprops_table

from astroquery.vizier import Vizier
#from astropy.coordinates import SkyCoord
import astropy.units as u
from scipy.ndimage import convolve
# from astropy.io import fits
# from astropy.coordinates import SkyCoord
# import glob
# import numpy as np
# import bottleneck as bn
# import win32com.client
# import pickle
# from astropy.stats import sigma_clip
# import math
# import sep
# import threading
# from astropy.utils.exceptions import AstropyUserWarning
# import warnings
# import subprocess

warnings.simplefilter('ignore', category=AstropyUserWarning)
mplstyle.use('fast')
mpl.rcParams['path.simplify'] = True
mpl.rcParams['path.simplify_threshold'] = 1.0

warnings.simplefilter("ignore", category=RuntimeWarning)

# def plot_bright_star_cutouts(outputimg, catalog, n=9, margin=1.2):
#     """
#     Plot a sqrt(n)x sqrt(n) grid of the n brightest sources from an SX++ catalog.

#     Parameters
#     ----------
#     outputimg : 2D numpy.ndarray
#         The image array.
#     catalog : astropy.table.Table
#         SX++ catalog with columns:
#         'pixel_centroid_x', 'pixel_centroid_y',
#         'peak_value_x', 'peak_value_y',
#         'kron_radius', 'ellipse_a', 'ellipse_b', 'ellipse_theta',
#         'auto_flux', 'auto_mag', 'elongation', 'ellipticity'.
#     n : int, optional
#         Number of brightest stars to plot (default=9).
#     margin : float, optional
#         Factor to pad around the Kron ellipse (default=1.2).
#     """
#     # # pick top-n brightest
#     # idx    = np.argsort(catalog['auto_flux'])[-n:][::-1]
#     # bright = catalog[idx]

#     # pick the 9 lowest-ellipticity objects
#     idx = np.argsort(catalog['ellipticity'])[:9]
#     bright = catalog[idx]

#     # grid size
#     m = int(np.ceil(np.sqrt(n)))
#     fig, axes = plt.subplots(m, m, figsize=(m*3, m*3))
#     axes = axes.flatten()

#     for ax, src in zip(axes, bright):
#         # convert 1-based FITS → 0-based NumPy
#         x0 = src['pixel_centroid_x'] - 1
#         y0 = src['pixel_centroid_y'] - 1

#         # ellipse semi‐axes (in pixels)
#         a = src['ellipse_a'] * src['kron_radius']
#         b = src['ellipse_b'] * src['kron_radius']
#         # half‐size of cutout box (odd total size)
#         r_pix = int(np.ceil(max(a, b) * margin))
#         size  = (2*r_pix + 1, 2*r_pix + 1)

#         # make the cutout
#         cut = Cutout2D(outputimg,
#                        position=(x0, y0),
#                        size=size,
#                        mode='partial',
#                        fill_value=np.nan)

#         ax.imshow(cut.data, origin='lower', cmap='gray')

#         # draw the elliptical Kron aperture
#         ell = Ellipse(xy=(r_pix, r_pix),
#                       width=2*a,
#                       height=2*b,
#                       angle=np.degrees(src['ellipse_theta']),
#                       edgecolor='red',
#                       facecolor='none',
#                       linewidth=1)
#         ax.add_patch(ell)

#         # mark the peak pixel
#         xp = src['peak_value_x'] - 1
#         yp = src['peak_value_y'] - 1
#         dx = xp - x0
#         dy = yp - y0
#         ax.scatter(r_pix + dx,
#                    r_pix + dy,
#                    marker='+',
#                    s=50,
#                    c='yellow')

#         # annotate flux & mag
#         ax.set_title(f"flux={src['auto_flux']:.0f},  mag={src['auto_mag']:.2f}",
#                      fontsize=8, color='white',
#                      backgroundcolor='black')
#         ax.axis('off')

#     plt.tight_layout()
#     plt.savefig(str(time.time())+'brightstarplots.png', dpi=300, bbox_inches='tight')
#     plt.close()


# def plot_sourcextractor_pp(outputimg,catalog,
#                             centroid_x='pixel_centroid_x', centroid_y='pixel_centroid_y',
#                             flux_radius='flux_radius', kron_radius='kron_radius',
#                             peak_x='peak_value_x', peak_y='peak_value_y', peak_value='peak_value'):
#     """
#     Overlay SourceXtractor++ detections on an Axes using PatchCollections for circles.

#     Parameters
#     ----------
#     ax : matplotlib.axes.Axes
#         The Axes to draw on (should already have the image plotted).
#     catalog : astropy.table.Table or pandas.DataFrame
#         Table containing at least the centroid, peak, flux_radius, and kron_radius columns.
#     centroid_x, centroid_y : str
#         Column names for pixel centroids.
#     flux_radius : str
#         Column name for flux radius values.
#     kron_radius : str
#         Column name for Kron radius values.
#     peak_x, peak_y : str
#         Column names for peak positions.
#     peak_value : str
#         Column name for peak intensity (used to size markers).
#     """
#     fig, ax = plt.subplots(figsize=(8, 8))
#     ax.imshow(outputimg, origin='lower', cmap='gray')
#     ax.set_xlabel('X pixel')
#     ax.set_ylabel('Y pixel')
#     ax.set_title('SourceXtractor++ detections')
#     # 1) plot pixel centroids (hollow cyan circles)
#     ax.scatter(catalog[centroid_x], catalog[centroid_y],
#                s=50, facecolors='none', edgecolors='cyan', label='Centroids')

#     # 2) plot peak positions (yellow stars sized by peak value)
#     sizes = (catalog[peak_value] / catalog[peak_value].max()) * 100
#     ax.scatter(catalog[peak_x], catalog[peak_y],
#                s=sizes, c='yellow', marker='*', label='Peaks')

#     # 3) build Circle patches for radii
#     flux_circs = [Circle((x, y), r) for x, y, r in zip(
#         catalog[centroid_x], catalog[centroid_y], catalog[flux_radius]
#     )]
#     kron_circs = [Circle((x, y), r) for x, y, r in zip(
#         catalog[centroid_x], catalog[centroid_y], catalog[kron_radius]
#     )]

#     # 4) create PatchCollections
#     flux_pc = PatchCollection(flux_circs,
#                               facecolor='none', edgecolor='red', linestyle='--', linewidths=1)
#     kron_pc = PatchCollection(kron_circs,
#                               facecolor='none', edgecolor='green', linestyle='-', linewidths=1)

#     # 5) add collections to Axes
#     ax.add_collection(flux_pc)
#     ax.add_collection(kron_pc)

#     # legend
#     ax.legend(loc='upper right')
#     plt.tight_layout()
#     plt.savefig(str(time.time())+'aftersourceplots.png', dpi=300, bbox_inches='tight')
#     plt.close()

def mask_hot_pixels_fast(img, sigma_thresh=8, sample_step=100, edge_mode='reflect'):
    """
    Quickly mark single‐pixel hot‐noise as NaN in a large (100 Mpx) 2D image.

    Strategy:
    1. Take a coarse subsample of img (every `sample_step`th pixel) to estimate
       median and σ.  (This is ≈(100 M / sample_step) elements—very fast.)
    2. Threshold the *entire* img array once: find coords where img > median + sigma_thresh·σ.
       (Vectorized, ~100 M comparisons in C.)
    3. For each threshold “candidate”, check its 3×3 neighborhood in Python and
       confirm it’s strictly larger than all 8 neighbors.  If so, set to NaN.

    Parameters
    ----------
    img : 2D np.ndarray, float or int
        Your raw image array.
    sigma_thresh : float
        How many sigma above the (estimated) background a pixel must be
        to qualify as a “hot” candidate.  Default ≈8σ picks only extreme outliers.
    sample_step : int
        Stride to subsample the image for background estimation.  E.g. 100 → use
        ~1% of all pixels (for 100 Mpx, that’s ~1 M samples).  Higher step → cheaper
        but cruder stats.
    edge_mode : str
        How to treat edges when checking neighbors.  (Passed to np.pad; e.g. 'mirror', 'constant'.)

    Returns
    -------
    out : 2D np.ndarray (same dtype as img, but with hot pixels replaced by np.nan)
    """
    # 1) Subsample every sample_step–th pixel to estimate median & σ
    #    We flatten and then take a 1D strided view—or just slice every sample_step in the raveled array.
    flat = img.ravel()
    sampled = flat[::sample_step]  # roughly (100 M / sample_step) points

    #   If img is integer‐typed, cast sampled to float so median/std aren’t truncated:
    sampled = sampled.astype(float, copy=False)

    median_est = np.median(sampled)
    sigma_est = np.std(sampled)

    thresh = median_est + sigma_thresh * sigma_est

    # 2) Vectorized threshold on the full image → boolean mask of candidates
    #    (This is ~100 M comparisons in optimized C, takes ~0.2–0.5 s on a modern CPU/GHz)
    candidates = np.argwhere(img > thresh)
    #   candidates.shape[0] = # of pixels > thresh.  Often ≪ 1% of total, maybe a few thousand.

    # 3) Now check each candidate’s 3×3 neighborhood “isolation”:
    #    Pad the image so we never index out of bounds at edges.
    padded = np.pad(img, pad_width=1, mode=edge_mode)

    out = img.astype(float, copy=True)  # make a float copy (so we can write nan)
    H, W = img.shape

    for (r, c) in candidates:
        pr, pc = r+1, c+1  # shift for padded
        center_val = padded[pr, pc]

        # Extract the 3×3 block around (pr, pc) in the padded array:
        #   neighbors = padded[pr-1:pr+2, pc-1:pc+2], but skip the center itself
        block = padded[pr-1:pr+2, pc-1:pc+2]
        # Check if center_val is strictly greater than all eight neighbors:
        #   Equivalent to: center_val > block.max() except block[1,1] is itself.
        #   We can zero out the center for the max‐check:
        block_center = block[1,1]
        block[1,1] = -np.inf  # temporarily make center “ignored”
        if center_val > block.max():
            # It is truly isolated (all 8 neighbors are smaller):
            out[r, c] = np.nan
        # restore center (not strictly necessary since we won’t reuse block)
        block[1,1] = block_center

    return out

# def fill_nans_with_local_mean(data, footprint=None):
#     """
#     Replace NaNs by the mean of their neighboring pixels.
#     - data: 2D numpy array with NaNs.
#     - footprint: kernel array of 0/1 defining neighborhood (default 3×3).
#     """
#     mask = np.isnan(data)
#     # zero-fill NaNs for convolution
#     filled = np.nan_to_num(data, copy=True)
#     if footprint is None:
#         footprint = np.ones((3,3), dtype=int)

#     # sum of neighbors (NaNs contributed as 0)
#     neighbor_sum   = convolve(filled,   footprint, mode='mirror')
#     # count of valid neighbors
#     neighbor_count = convolve(~mask,    footprint, mode='mirror')

#     # only replace where count>0
#     replace_idxs = mask & (neighbor_count>0)
#     data_out = data.copy()
#     data_out[replace_idxs] = neighbor_sum[replace_idxs] / neighbor_count[replace_idxs]
#     return data_out

def calculate_donut_distance(outputimg, catalog, search_radius_factor=3.0):
    x_cent = catalog['pixel_centroid_x'] - 1  # FITS to NumPy
    y_cent = catalog['pixel_centroid_y'] - 1
    kron_r = catalog['kron_radius']

    x_dists = []
    y_dists = []
    total_dists = []

    for x0, y0, kr in zip(x_cent, y_cent, kron_r):
        r_search = int(np.ceil(kr * search_radius_factor))
        size = (2 * r_search + 1, 2 * r_search + 1)

        try:
            # round and cast to int
            # size = int(np.round(size))
            # Unpack, round, repack:
            # if isinstance(size, (tuple, list, np.ndarray)):
            #     ny, nx = size
            #     ny = int(np.round(ny))
            #     nx = int(np.round(nx))
            #     size = (ny, nx)
            # else:
            #     size = int(np.round(size))
            # x0i, y0i = int(np.round(x0)), int(np.round(y0))

            # ny, nx = outputimg.shape
            # half = size // 2

            # # figure out how many pixels we can actually grab
            # xmin = max( 0, x0i - half )
            # xmax = min( nx, x0i + half + (size % 2) )
            # ymin = max( 0, y0i - half )
            # ymax = min( ny, y0i + half + (size % 2) )

            # real_ny, real_nx = ymax - ymin, xmax - xmin

            # # if either dimension is ≤ 0, skip this frame
            # if real_ny <= 0 or real_nx <= 0:
            # 1) Round & cast size to int or (int, int)
            if hasattr(size, "__iter__") and len(size) == 2:
                size = tuple(int(np.round(s)) for s in size)
            else:
                size = int(np.round(size))

            # 2) Compute half-sizes for Y and X
            if isinstance(size, tuple):
                half_y, half_x = size[0] // 2, size[1] // 2
            else:
                half_y = half_x = size // 2

            # 3) Round & cast your center too
            y0i, x0i = int(np.round(y0)), int(np.round(x0))

            # 4) Clamp to image boundaries
            ny, nx = outputimg.shape
            ymin = max(0, y0i - half_y)
            ymax = min(ny, y0i + half_y + (size[0]%2 if isinstance(size, tuple) else size%2))
            xmin = max(0, x0i - half_x)
            xmax = min(nx, x0i + half_x + (size[1]%2 if isinstance(size, tuple) else size%2))

            # 5) If it collapsed, bail out
            if (ymax - ymin) <= 0 or (xmax - xmin) <= 0:
                # e.g. log it and return NaN or zero distance
                # Ensure placeholders are appended
                x_dists.append(np.nan)
                y_dists.append(np.nan)
                total_dists.append(np.nan)
            else:
                # Cutout centered on centroid
                real_size = (ymax - ymin, xmax - xmin)
                cutout = Cutout2D(outputimg, position=(x0, y0), size=real_size, mode='partial', fill_value=np.nan)

                # Find brightest pixel in the cutout
                if np.all(np.isnan(cutout.data)):
                    # No valid data; skip or set distance to NaN
                    x_dists.append(np.nan)
                    y_dists.append(np.nan)
                    total_dists.append(np.nan)
                    continue

                local_max_pos = np.unravel_index(np.nanargmax(cutout.data), cutout.data.shape)
                y_peak_local, x_peak_local = local_max_pos

                # Calculate offset relative to cutout center
                dx = x_peak_local - r_search
                dy = y_peak_local - r_search
                dist = np.hypot(dx, dy)

                x_dists.append(abs(dx))
                y_dists.append(abs(dy))
                total_dists.append(dist)
        except:
            plog ("there is an occasional cutout area but to find....")
            plog(traceback.format_exc())
            plog (size)
            plog (x0)
            plog (y0)
            # Ensure placeholders are appended
            x_dists.append(np.nan)
            y_dists.append(np.nan)
            total_dists.append(np.nan)

    catalog['x_donut_distance'] = x_dists
    catalog['y_donut_distance'] = y_dists
    catalog['total_donut_distance'] = total_dists

    return catalog

def create_gaussian_psf(fwhm, size=11):
    """
    Create a 2D Gaussian kernel with a given FWHM.

    Parameters:
    - fwhm: Full Width at Half Maximum of the Gaussian PSF.
    - size: Size of the kernel (should be large enough to capture most of the PSF).

    Returns:
    - psf: 2D numpy array representing the Gaussian PSF.
    """
    sigma = fwhm / (2 * np.sqrt(2 * np.log(2)))  # Convert FWHM to sigma
    center = size // 2
    y, x = np.mgrid[0:size, 0:size]
    psf = np.exp(-((x - center)**2 + (y - center)**2) / (2 * sigma**2))
    psf /= psf.sum()  # Normalize to ensure total flux is 1
    return psf

def add_star_with_psf(image_array, x, y, flux, psf):
    """
    Add a single star with a Gaussian PSF to the image array.

    Parameters:
    - image_array: 2D numpy array representing the image.
    - x, y: Pixel coordinates of the star.
    - flux: Total flux of the star.
    - psf: 2D numpy array representing the normalized PSF.
    """
    psf_size = psf.shape[0]
    psf_center = psf_size // 2
    x_start = max(0, x - psf_center)
    x_end = min(image_array.shape[1], x + psf_center + 1)
    y_start = max(0, y - psf_center)
    y_end = min(image_array.shape[0], y + psf_center + 1)

    psf_x_start = psf_center - (x - x_start)
    psf_x_end = psf_center + (x_end - x)
    psf_y_start = psf_center - (y - y_start)
    psf_y_end = psf_center + (y_end - y)

    # Add scaled PSF to the image
    image_array[y_start:y_end, x_start:x_end] += flux * psf[
        psf_y_start:psf_y_end, psf_x_start:psf_x_end
    ]

#This function computes the factor of the argument passed
def print_factors(x):
   print("The factors of",x,"are:")
   for i in range(1, x + 1):
       if x % i == 0:
           print(i)

def sun_az_alt_now(site_coordinates):

    altazframe=AltAz(obstime=Time.now(), location=site_coordinates)
    sun_coords=get_sun(Time.now()).transform_to(altazframe)
    return sun_coords.az.degree, sun_coords.alt.degree


def mid_stretch_jpeg(data):
    """
    This product is based on software from the PixInsight project, developed by
    Pleiades Astrophoto and its contributors (http://pixinsight.com/).

    And also Tim Beccue with a minor flourishing/speedup by Michael Fitzgerald.
    """
    target_bkg = 0.25
    shadows_clip = -1.25

    """ Stretch the image.
    Args:
        data (np.array): the original image data array.

    Returns:
        np.array: the stretched image data
    """

    try:
        data = data / bn.nanmax(data)
    except:
        data = data  # NB this avoids div by 0 is image is a very flat bias

    """Return the average deviation from the median.

    Args:
        data (np.array): array of floats, presumably the image data
    """
    median = bn.nanmedian(data.ravel())
    n = data.size
    avg_dev = np.sum(np.absolute(data-median) / n)
    c0 = np.clip(median + (shadows_clip * avg_dev), 0, 1)
    x = median - c0

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
    zeros = x == 0
    halfs = x == target_bkg
    ones = x == 1
    others = np.logical_xor((x == x), (zeros + halfs + ones))
    x[zeros] = 0
    x[halfs] = 0.5
    x[ones] = 1
    x[others] = (target_bkg - 1) * x[others] / \
        ((((2 * target_bkg) - 1) * x[others]) - target_bkg)
    m = x.reshape(shape)

    stretch_params = {
        "c0": c0,
        # "c1": 1,
        "m": m
    }

    m = stretch_params["m"]
    c0 = stretch_params["c0"]
    above = data >= c0

    # Clip everything below the shadows clipping point
    data[data < c0] = 0
    # For the rest of the pixels: apply the midtones transfer function
    x = (data[above] - c0)/(1 - c0)

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
    zeros = x == 0
    halfs = x == m
    ones = x == 1
    others = np.logical_xor((x == x), (zeros + halfs + ones))
    x[zeros] = 0
    x[halfs] = 0.5
    x[ones] = 1
    x[others] = (m - 1) * x[others] / ((((2 * m) - 1) * x[others]) - m)
    data[above] = x.reshape(shape)

    return data

def fit_moffat_worker(args):
    cutout, position = args
    x_center, y_center = position
    try:
        amplitude = np.max(cutout)
        y, x = np.mgrid[:cutout.shape[0], :cutout.shape[1]]

        moffat_init = models.Moffat2D(
            amplitude=amplitude,
            x_0=cutout.shape[1] / 2,
            y_0=cutout.shape[0] / 2,
            gamma=2,
            alpha=1.5
        )

        fitter = fitting.LevMarLSQFitter()
        moffat_fit = fitter(moffat_init, x, y, cutout)

        gamma = moffat_fit.gamma.value
        alpha = moffat_fit.alpha.value

        fwhm = 2 * gamma * np.sqrt(2**(1/alpha) - 1)
        return fwhm
    except Exception as e:
        print(f"[Worker Error] Problem fitting cutout at position ({x_center}, {y_center}): {e}")
        print(traceback.format_exc())
        return None

# Note this is a thread!
def dump_main_data_out_to_post_exposure_subprocess(payload, post_processing_subprocess):
    """ Send the data to the post-processing subprocess."""
    try:
        # Manual debug flag
        debug_post_processing_subprocess = False
        if debug_post_processing_subprocess:
            pickle.dump(payload, open('subprocesses/testpostprocess.pickle','wb'))
            breakpoint()
        else:
            pickle.dump(payload, post_processing_subprocess.stdin)
            post_processing_subprocess.stdin.close()  # Ensure the input stream is closed
    except Exception as e:
        plog.warn(f"Problem in the post_processing_subprocess pickle dump: {e}")
        plog.warn(traceback.format_exc())


# Note this is a thread!
def write_raw_file_out(packet):

    (raw, raw_name, hdudata, hduheader, frame_type,
     current_icrs_ra, current_icrs_dec, altpath, altfolder) = packet

    # Make sure normal paths exist
    os.makedirs(
        g_dev['cam'].camera_path + g_dev["day"], exist_ok=True, mode=0o777
    )
    os.makedirs(
        g_dev['cam'].camera_path + g_dev["day"] + "/raw/", exist_ok=True, mode=0o777
    )
    os.makedirs(
        g_dev['cam'].camera_path + g_dev["day"] + "/reduced/", exist_ok=True, mode=0o777
    )
    os.makedirs(
        g_dev['cam'].camera_path + g_dev["day"] + "/calib/", exist_ok=True, mode=0o777)

    # Make  sure the alt paths exist
    if raw == 'raw_alt_path':
        os.makedirs(
            altpath + g_dev["day"], exist_ok=True, mode=0o777
        )
        os.makedirs(
            altpath + g_dev["day"] + "/raw/", exist_ok=True, mode=0o777
        )
        os.makedirs(
            altpath + g_dev["day"] + "/reduced/", exist_ok=True, mode=0o777
        )
        os.makedirs(
            altpath + g_dev["day"] + "/calib/", exist_ok=True, mode=0o777)

    hdu = fits.PrimaryHDU()
    hdu.data = hdudata
    hdu.header = hduheader
    hdu.header["DATE"] = (
        datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
        "Date FITS file was written",
    )

    hdu.writeto(raw_name, overwrite=True, output_verify='silentfix')
    try:
        hdu.close()
    except:
        pass
    del hdu


def gaussian(x, amplitude, mean, stddev):
    return amplitude * np.exp(-((x - mean) / 4 / stddev)**2)

# https://stackoverflow.com/questions/9111711/get-coordinates-of-local-maxima-in-2d-array-above-certain-value


def localMax(a, include_diagonal=True, threshold=-np.inf):
    # Pad array so we can handle edges
    ap = np.pad(a, ((1, 1), (1, 1)), constant_values=-np.inf)

    # Determines if each location is bigger than adjacent neighbors
    adjacentmax = (
        (ap[1:-1, 1:-1] > threshold) &
        (ap[0:-2, 1:-1] <= ap[1:-1, 1:-1]) &
        (ap[2:,  1:-1] <= ap[1:-1, 1:-1]) &
        (ap[1:-1, 0:-2] <= ap[1:-1, 1:-1]) &
        (ap[1:-1, 2:] <= ap[1:-1, 1:-1])
    )
    if not include_diagonal:
        return np.argwhere(adjacentmax)

    # Determines if each location is bigger than diagonal neighbors
    diagonalmax = (
        (ap[0:-2, 0:-2] <= ap[1:-1, 1:-1]) &
        (ap[2:, 2:] <= ap[1:-1, 1:-1]) &
        (ap[0:-2, 2:] <= ap[1:-1, 1:-1]) &
        (ap[2:, 0:-2] <= ap[1:-1, 1:-1])
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
    readmodenum = c_int32(2)
    CONTROL_BRIGHTNESS = c_int(0)
    CONTROL_GAIN = c_int(6)
    CONTROL_USBTRAFFIC = c_int(6)

    CONTROL_SPEED = c_int(6)
    CONTROL_OFFSET = c_int(7)
    CONTROL_EXPOSURE = c_int(8)
    CAM_GPS = c_int(36)
    CAM_HUMIDITY = c_int(62)  # WER added these two new attributes.
    CAM_PRESSURE = c_int(63)
    CONTROL_CURTEMP = c_int(14)  # (14)
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
        self.so.SetQHYCCDResolution.argtypes = [
            c_void_p, c_uint32, c_uint32, c_uint32, c_uint32]
        self.so.GetQHYCCDSingleFrame.argtypes = [
            c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.GetQHYCCDChipInfo.argtypes = [
            c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
        self.so.GetQHYCCDLiveFrame.argtypes = [
            c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
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
    qhycam_id = cam_id
    init_camera_param(qhycam_id)
    qhycam.camera_params[qhycam_id]['connect_to_pc'] = True


@CFUNCTYPE(None, c_char_p)
def pnp_out(cam_id):
    print("cam   - %s" % cam_id.decode('utf-8'))

# MTF - THIS IS A QHY FUNCTION THAT I HAVEN"T FIGURED OUT WHETHER IT IS MISSION CRITICAL OR NOT
# WER - It is mission critical. Do not disturb!


def init_camera_param(cam_id):
    # This function assumes we're dealing with the main camera. It will have to be updated
    # if this is not always the case.
    main_camera_name = g_dev['obs'].config['device_roles']['main_cam']
    main_camera_config_settings = g_dev['obs'].config['camera'][main_camera_name]['settings']
    if not qhycam.camera_params.keys().__contains__(cam_id):
        qhycam.camera_params[cam_id] = {'connect_to_pc': False,
                                        'connect_to_sdk': False,
                                        'EXPOSURE': c_double(1000.0 * 1000.0),
                                        # 'GAIN': c_double(54.0),
                                        'GAIN': c_double(54.0),
                                        'CONTROL_BRIGHTNESS': c_int(0),
                                        # 'CONTROL_GAIN': c_int(6),
                                        'CONTROL_GAIN': c_int(6),
                                        # 'CONTROL_USBTRAFFIC': c_int(6),
                                        'CONTROL_SPEED': c_int(6),
                                        'CONTROL_USBTRAFFIC': c_int(6),
                                        'CONTROL_EXPOSURE': c_int(8),
                                        # 'CONTROL_CURTEMP': c_int(14),
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
                                        # 'read_mode': c_uint8(0),
                                        'channels': c_uint32(),
                                        'read_mode_number': c_uint32(main_camera_config_settings['direct_qhy_readout_mode']),
                                        'read_mode_index': c_uint32(main_camera_config_settings['direct_qhy_readout_mode']),
                                        'read_mode_name': c_char('-'.encode('utf-8')),
                                        'prev_img_data': c_void_p(0),
                                        'prev_img': None,
                                        'handle': None,
                                        }


def next_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(
        g_dev['obs'].obsid_path + "ptr_night_shelf/" + pCamera + str(g_dev['obs'].name))
    sKey = "Sequence"
    try:
        seq = camShelf[sKey]  # get an 8 character string
    except:
        plog("Failed to get seq key, starting from zero again")
        seq = 1
    seqInt = int(seq)
    seqInt += 1
    seq = ("0000000000" + str(seqInt))[-8:]
    camShelf["Sequence"] = seq
    camShelf.close()
    SEQ_Counter = seq
    return seq


def test_sequence(pCamera):
    global SEQ_Counter
    camShelf = shelve.open(
        g_dev['obs'].obsid_path + "ptr_night_shelf/" + pCamera + str(g_dev['obs'].name))
    sKey = "Sequence"
    seq = camShelf[sKey]  # get an 8 character string
    camShelf.close()
    SEQ_Counter = seq
    return seq


def reset_sequence(pCamera):
    try:
        # Remove any broken files first.
        temp_shelf_list=glob.glob(g_dev['obs'].obsid_path + "ptr_night_shelf/" +
        str(pCamera) + str(g_dev['obs'].name)+ '*')
        for file in temp_shelf_list:
            try:
                os.remove(file)
            except:
                pass

        camShelf = shelve.open(
            g_dev['obs'].obsid_path + "ptr_night_shelf/" +
            str(pCamera) + str(g_dev['obs'].name)
        )
        seqInt = int(-1)
        seqInt += 1
        seq = ("0000000000" + str(seqInt))[-8:]
        plog("Making new seq: ", pCamera, seq)
        camShelf["Sequence"] = seq
        camShelf.close()
        return seq
    except:
        plog(traceback.format_exc())
        plog("Nothing on the cam shelf in reset_sequence")
        return None

class Camera:
    """A camera instrument.

    The filter, focuser, rotator must be set up prior to camera.
    Since this is a class definition we need to pre-enter with a list of classes
    to be created by a camera factory.
    """

    def __init__(self, driver: str, name: str, site_config: dict, observatory: 'Observatory'):
        """
        Added monkey patches to make ASCOM/Maxim/TheSkyX/QHY differences
        go away from the bulk of the in-line code.
        """
        datetime_at_init = datetime.now(tz=timezone.utc)

        self.last_user_name = "none"
        self.last_user_id = "none"
        self.user_name = "none"
        self.user_id = "none"

        self.name = name
        self.driver = driver

        # Set the dummy flag, which toggles simulator mode
        self.dummy = (driver == 'dummy')

        # Configure the camera role, if it exists
        # Current design allows for only one role per device
        # We can add more roles by changing self.role to a list and adjusting any references
        self.role = None
        for role, device in site_config['device_roles'].items():
            if device == name:
                self.role = role
                break

        g_dev[name + "_cam_retry_driver"] = driver
        g_dev[name + "_cam_retry_name"] = name
        g_dev[name + "_cam_retry_config"] = site_config
        g_dev[name + "_cam_retry_doit"] = False
        g_dev[name] = self
        if self.role == "main_cam":  # NB  Default sets up Selected 'cam'
            g_dev["cam"] = self

        self.obs = observatory # use this to access the parent observatory object
        self.site_config = site_config
        self.config = site_config['camera'][name] # sometimes it's useful to access just this camera's config
        self.settings = self.config['settings']
        self.alias = site_config["camera"][name]["name"]


        if not self.dummy:
            win32com.client.pythoncom.CoInitialize()
            plog(driver, name)

            if not driver == "QHYCCD_Direct_Control" and not driver == 'zwo_native_driver':
                self.camera = win32com.client.Dispatch(driver)
            else:
                self.camera = None
        else:
            self.camera = None

        # This is needed for TheSkyx (and maybe future programs) where the
        self.async_exposure_lock = False
        # exposure has to be called from a separate thread and then waited
        # for in the main thread

        # Sets up paths and structures
        self.obsid_path = g_dev['obs'].obsid_path
        if not os.path.exists(self.obsid_path):
            os.makedirs(self.obsid_path, mode=0o777)
        self.local_calibration_path = g_dev['obs'].local_calibration_path
        if not os.path.exists(self.local_calibration_path):
            os.makedirs(self.local_calibration_path, mode=0o777)

        self.archive_path = self.site_config["archive_path"] + \
            self.site_config['obs_id'] + '/' + "archive/"
        if not os.path.exists(self.site_config["archive_path"] + '/' + self.site_config['obs_id']):
            os.makedirs(self.site_config["archive_path"] +
                        '/' + self.site_config['obs_id'], mode=0o777)
        if not os.path.exists(self.site_config["archive_path"] + '/' + self.site_config['obs_id'] + '/' + "archive/"):
            os.makedirs(self.site_config["archive_path"] + '/' +
                        self.site_config['obs_id'] + '/' + "archive/", mode=0o777)
        self.camera_path = self.archive_path + self.alias + "/"
        if not os.path.exists(self.camera_path):
            os.makedirs(self.camera_path, mode=0o777)
        self.alt_path = self.site_config[
            "alt_path"
        ] + '/' + self.site_config['obs_id'] + '/'  # NB NB this should come from config file, it is site dependent.
        if not os.path.exists(self.site_config[
            "alt_path"
        ]):
            os.makedirs(self.site_config[
                "alt_path"
            ], mode=0o777)

        if not os.path.exists(self.alt_path):
            os.makedirs(self.alt_path, mode=0o777)

        # Just need to initialise this filter thing
        self.current_offset = 0
        self.current_filter = None

        self.updates_paused = False

        """
        This section loads in the calibration files for flash calibrations
        """
        plog("loading flash dark, bias and flat master frames if available")
        self.biasFiles = {}
        self.darkFiles = {}
        self.flatFiles = {}
        self.bpmFiles = {}

        g_dev['obs'].obs_id
        tempfrontcalib = g_dev['obs'].obs_id + '_' + self.alias + '_'

        file_descriptors = [
            {"filename": "BIAS_master_bin1.fits", "dict_key": "1", "log_message": "Bias frame for Binning 1 not available", "dict": self.biasFiles},
            {"filename": "DARK_master_bin1.fits", "dict_key": "1", "log_message": "Long Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "halfsecondDARK_master_bin1.fits", "dict_key": "halfsec_exposure_dark", "log_message": "0.5s Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "2secondDARK_master_bin1.fits", "dict_key": "twosec_exposure_dark", "log_message": "2.0s Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "10secondDARK_master_bin1.fits", "dict_key": "tensec_exposure_dark", "log_message": "10.0s Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "tensecBIASDARK_master_bin1.fits", "dict_key": "tensec_exposure_biasdark", "log_message": "10.0s Bias Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "30secondDARK_master_bin1.fits", "dict_key": "thirtysec_exposure_dark", "log_message": "30.0s Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "thirtysecBIASDARK_master_bin1.fits", "dict_key": "thirtysec_exposure_biasdark", "log_message": "30.0s Bias Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "broadbandssDARK_master_bin1.fits", "dict_key": "broadband_ss_dark", "log_message": "Broadband Smartstack Length Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "broadbandssBIASDARK_master_bin1.fits", "dict_key": "broadband_ss_biasdark", "log_message": "Broadband Smartstack Length Bias Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "narrowbandssDARK_master_bin1.fits", "dict_key": "narrowband_ss_dark", "log_message": "Narrowband Smartstack Length Dark frame for Binning 1 not available", "dict": self.darkFiles},
            {"filename": "narrowbandssBIASDARK_master_bin1.fits", "dict_key": "narrowband_ss_biasdark", "log_message": "Narrowband Smartstack Length Bias Dark frame for Binning 1 not available", "dict": self.darkFiles},
        ]

        for descriptor in file_descriptors:
            try:
                file_path = f"{self.local_calibration_path}archive/{self.alias}/calibmasters/{tempfrontcalib}{descriptor['filename']}"
                tempframe = fits.open(file_path)
                tempframe = np.array(tempframe[0].data, dtype=np.float32)
                descriptor['dict'].update({descriptor['dict_key']: tempframe})
                del tempframe
            except:
                plog(descriptor['log_message'])


        try:

            tempbpmframe = np.load(self.local_calibration_path + "archive/" +
                                   self.alias + "/calibmasters/" + tempfrontcalib + "badpixelmask_bin1.npy")
            # For live observing, ignore bad pixels on crusty edges
            # At the edges they can be full columns or large patches of
            # continuous areas which take too long to interpolate quickly.
            # The full PIPE run does not ignore these.
            tempbpmframe[:, :75] = False
            tempbpmframe[:75, :] = False
            tempbpmframe[-75:, :] = False
            tempbpmframe[:, -75:] = False
            self.bpmFiles.update({'1': tempbpmframe})
            del tempbpmframe
        except:
            plog("Bad Pixel Mask for Binning 1 not available")

        try:
            fileList = glob.glob(self.local_calibration_path + "archive/" +
                                 self.alias + "/calibmasters/masterFlat*_bin1.npy")
            for file in fileList:
                self.flatFiles.update(
                    {file.split("_")[1].replace('.npy', '') + '_bin1': file})
            # To supress occasional flatfield div errors
            np.seterr(divide="ignore")
        except:
            plog("Flat frames not loaded or available")

        self.shutter_open = False  # Initialise
        self.substacker = False  # Initialise
        self.pwm_percent = ' na%'
        self.spt_C = '  naC'
        self.temp_C = ' naC'
        self.hum_percent = ' na%'

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
            self.zwo=False
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
                plog("ERROR:  ASCOM camera is not connected:  ",
                     self._connect(True))

            self.imagesize_x = self.camera.CameraXSize
            self.imagesize_y = self.camera.CameraYSize

        elif driver == "CCDSoft2XAdaptor.ccdsoft5Camera" or driver =="TheSky64.ccdsoftCamera":
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
            self.zwo=False
            self.maxim = False
            self.ascom = False
            self.theskyx = True
            self.qhydirect = False
            plog("TheSkyX is connected:  ")
            # self.app = win32com.client.Dispatch(
            #     "CCDSoft2XAdaptor.ccdsoft5Camera")

            self.app = win32com.client.Dispatch(
                driver)

            # Initialise Camera Size here
            # Take a quick cheeky frame to get imagesize
            tempcamera = win32com.client.Dispatch(self.driver)
            tempcamera.Connect()
            self._stop_expose()
            tempcamera.Frame = 1
            tempcamera.ExposureTime = 0
            tempcamera.ImageReduction = 0
            tempcamera.TakeImage()
            imageTempOpen = fits.open(tempcamera.LastImageFileName, uint=False)[
                0].data.astype("float32")
            del tempcamera
            try:
                os.remove(self.camera.LastImageFileName)
            except Exception as e:
                plog("Could not remove theskyx image file: ", e)
            self.imagesize_x = int(imageTempOpen.shape[0])
            self.imagesize_y = int(imageTempOpen.shape[1])
            del imageTempOpen

        elif driver == "QHYCCD_Direct_Control":
            global qhycam

            # plog("TRYING TO cycle the QHY camera power via Ultimate Powerbox V2, if it exists.")

            try:
                self.power_box_driver = self.config["switch_driver"]
                pb = win32com.client.Dispatch(self.power_box_driver)
                #breakpoint()  #NB NB make sure only one PowerBox process is running or the next line Throws an exception.
                pb.connected = True
                n_switches = pb.MaxSwitch
                #To inspect, try:
                # for ii in range(n_switches):
                #     time.sleep(0.1)
                #     print(ii, pb.getSwitchValue(ii))

                #First we need to turn everything on
                for ii in range(n_switches):
                    time.sleep(0.1)
                    pb.setSwitchValue(ii, 1)
                #Now camera off
                pb.SetSwitchValue(6, 0)
                print("Cam power is off for 5 sec.")
                time.sleep(5)

                print("Cam power is turning on ")
                pb.SetSwitchValue(6, 1)
                time.sleep(10)
                plog("Cam power is, after 10 sec:  ", pb.getSwitchValue(6))

                #A double check
                # for ii in range(n_switches):
                #     print(ii, pb.GetSwitchValue(ii))


            except:
                plog("Failed to connect to Powerbox V2, sorry!")


            plog("Connecting directly to QHY")
            qhycam = Qcam(os.path.join("support_info/qhysdk/x64/qhyccd.dll"))

            qhycam.so.RegisterPnpEventIn(pnp_in)
            qhycam.so.RegisterPnpEventOut(pnp_out)
            qhycam.so.InitQHYCCDResource()
            qhycam.camera_params[qhycam_id]['handle'] = qhycam.so.OpenQHYCCD(
                qhycam_id)
            if qhycam.camera_params[qhycam_id]['handle'] is None:
                print('open camera error %s' % qhycam_id)

            read_mode = self.settings['direct_qhy_readout_mode']
            numModes = c_int32()
            success = qhycam.so.SetQHYCCDReadMode(
                qhycam.camera_params[qhycam_id]['handle'], read_mode)

            qhycam.camera_params[qhycam_id]['stream_mode'] = c_uint8(
                qhycam.stream_single_mode)
            success = qhycam.so.SetQHYCCDStreamMode(
                qhycam.camera_params[qhycam_id]['handle'], qhycam.camera_params[qhycam_id]['stream_mode'])

            success = qhycam.so.InitQHYCCD(
                qhycam.camera_params[qhycam_id]['handle'])

            mode_name = create_string_buffer(qhycam.STR_BUFFER_SIZE)
            # 0 is Photographic DSO 16 bit
            qhycam.so.GetReadModeName(qhycam_id, read_mode, mode_name)
            read_mode_name_str = mode_name.value.decode(
                'utf-8').replace(' ', '_')
            plog("Read Mode: " + read_mode_name_str)

            success = qhycam.so.SetQHYCCDBitsMode(
                qhycam.camera_params[qhycam_id]['handle'], c_uint32(qhycam.bit_depth_16))

            success = qhycam.so.GetQHYCCDChipInfo(qhycam.camera_params[qhycam_id]['handle'],
                                                  byref(
                                                      qhycam.camera_params[qhycam_id]['chip_width']),
                                                  byref(
                                                      qhycam.camera_params[qhycam_id]['chip_height']),
                                                  byref(
                                                      qhycam.camera_params[qhycam_id]['image_width']),
                                                  byref(
                                                      qhycam.camera_params[qhycam_id]['image_height']),
                                                  byref(
                                                      qhycam.camera_params[qhycam_id]['pixel_width']),
                                                  byref(
                                                      qhycam.camera_params[qhycam_id]['pixel_height']),
                                                  byref(qhycam.camera_params[qhycam_id]['bits_per_pixel']))

            qhycam.camera_params[qhycam_id]['mem_len'] = qhycam.so.GetQHYCCDMemLength(
                qhycam.camera_params[qhycam_id]['handle'])
            c_w = qhycam.camera_params[qhycam_id]['chip_width'].value
            c_h = qhycam.camera_params[qhycam_id]['chip_height'].value
            i_w = qhycam.camera_params[qhycam_id]['image_width'].value
            i_h = qhycam.camera_params[qhycam_id]['image_height'].value
            o_w = c_w - i_w
            o_h = c_h - i_h

            qhycam.camera_params[qhycam_id]['prev_img_data'] = (
                c_uint16 * int(qhycam.camera_params[qhycam_id]['mem_len'] / 2))()

            success = qhycam.QHYCCD_ERROR

            qhycam.so.SetQHYCCDResolution(qhycam.camera_params[qhycam_id]['handle'], c_uint32(0), c_uint32(0), c_uint32(i_w),
                                           c_uint32(i_h))
            #qhycam.so.SetQHYCCDResolution(qhycam.camera_params[qhycam_id]['handle'], c_uint32(0), c_uint32(0), c_uint32(c_w),
            #                              c_uint32(c_h))
            image_width_byref = c_uint32()
            image_height_byref = c_uint32()
            bits_per_pixel_byref = c_uint32()

            success = qhycam.so.SetQHYCCDParam(
                qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(20000))
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_GAIN, c_double(
                float(self.settings['direct_qhy_gain'])))
            success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_OFFSET, c_double(
                float(self.settings['direct_qhy_offset'])))
            #success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_USBTRAFFIC,c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_usb_speed'])))
            #success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_USBTRAFFIC,c_double(float(self.config["camera"][self.name]["settings"]['direct_qhy_usb_traffic'])))

            if self.settings['set_qhy_usb_speed']:
                success = qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_SPEED, c_double(
                    float(self.settings['direct_qhy_usb_traffic'])))
            plog('Set QHY conversion Gain: ',
                 self.settings['direct_qhy_gain'])
            plog('Set QHY Offset: ',
                 self.settings['direct_qhy_offset'])
            # NB NB ideally we should read this back to verify.
            plog('Set QHY USB speed to: ',
                 self.settings['direct_qhy_usb_traffic'])

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
            self.zwo=False
            self.maxim = False
            self.ascom = False
            self.theskyx = False
            self.qhydirect = True

            # Initialise Camera Size here
            self.imagesize_x = int(i_h)   #20250101  Was i_h   WER
            self.imagesize_y = int(i_w)

        elif driver == 'zwo_native_driver':

            sdk_path = "support_info/ASISDK/lib/x64/ASICamera2.dll"
            asi.init(sdk_path)
            # Check connected cameras
            num_cameras = asi.get_num_cameras()
            if num_cameras == 0:
                print("No ZWO cameras detected.")
            print(f"Number of cameras detected: {num_cameras}")

            # Get camera details
            camera_index = 0 # 0 is first camera
            global zwocamera
            zwocamera = asi.Camera(camera_index)
            camera_info = zwocamera.get_camera_property()
            print(f"Using camera: {camera_info['Name']}")

            # Configure camera settings
            gain = 150 # low read noise, high gain for short exposures.
            zwocamera.set_control_value(asi.ASI_GAIN, gain)
            zwocamera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, 40)  # Optional: Adjust for your system
            zwocamera.set_control_value(asi.ASI_BRIGHTNESS, 100)  # Optional: Adjust for your system
            zwocamera.set_image_type(asi.ASI_IMG_RAW16)  # Use RAW8 image type



            # NB NB NB Considerputting this up higher.
            # plog("Maxim camera is initializing.")
            self._connected = self._zwo_connected
            self._connect = self._zwo_connect
            self._set_setpoint = self._zwo_set_setpoint
            self._setpoint = self._zwo_setpoint
            self._temperature = self._zwo_temperature
            self._cooler_on = self._zwo_cooler_on
            self._set_cooler_on = self._zwo_set_cooler_on
            self._expose = self._zwo_expose
            self._stop_expose = self._zwo_stop_expose
            self._imageavailable = self._zwo_imageavailable
            self._getImageArray = self._zwo_getImageArray

            self.description = "ZWO"
            self.zwo=True
            self.maxim = False
            self.ascom = False
            self.theskyx = False
            self.qhydirect = False
            # plog("Maxim is connected:  ", self._connect(True))
            # self.app = win32com.client.Dispatch("Maxim.Application")
            # plog(self.camera)
            # self.camera.SetFullFrame()
            # self.camera.SetFullFrame

            # Quick shot to get camera size
            # Get image dimensions from ROI
            roi_format = zwocamera.get_roi_format()

            self.imagesize_x = roi_format[0]
            self.imagesize_y = roi_format[1]

            # plog("Control is via Maxim camera interface, not ASCOM.")
            # plog("Please note telescope is NOT connected to Maxim.")

        elif driver == 'maxim':
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
            self.zwo=False
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

        elif driver == 'dummy':
            plog("Simulated camera is initializing.")
            self._connected = self._dummy_connected
            self._connect = self._dummy_connect
            self._set_setpoint = self._dummy_set_setpoint
            self._setpoint = self._dummy_setpoint
            self._temperature = self._dummy_temperature
            self._cooler_on = self._dummy_cooler_on
            self._set_cooler_on = self._dummy_set_cooler_on
            self._expose = self._dummy_expose
            self._stop_expose = self._dummy_stop_expose
            self._imageavailable = self._dummy_imageavailable
            self._getImageArray = self._dummy_getImageArray

            self.description = "Simulated Camera"
            self.zwo=False
            self.maxim = False
            self.ascom = False
            self.theskyx = False
            self.qhydirect = False
            plog("Simulated camera is connected:  ", self._connect(True))

            self.pixscale = 0.75
            self.imagesize_x = 2400
            self.imagesize_y = 2400


        # Before anything, abort any exposures because sometimes a long exposure
        # e.g. 500s could keep on going with theskyx (and maybe Maxim)
        # and still be going on at a restart and crash the connection
        try:
            self._stop_expose()
        except:
            pass

        # Camera cooling setup
        # This is the config setpoint

        self.temp_setpoint_by_season = self.settings.get('set_temp_setpoint_by_season', False)
        if self.temp_setpoint_by_season:

            tempmonth = datetime_at_init.month
            tempday= datetime_at_init.day

            if tempmonth == 12 or tempmonth == 1 or (tempmonth ==11 and tempday >15) or (tempmonth ==2 and tempday <=15):
                self.setpoint = float(
                    self.settings['temp_setpoint_nov_to_feb'][0])
                self.day_warm = self.settings['temp_setpoint_nov_to_feb'][2]
                self.day_warm_degrees = float(
                    self.settings['temp_setpoint_nov_to_feb'][1])

            elif tempmonth == 3 or tempmonth == 4 or (tempmonth ==2 and tempday >15) or (tempmonth ==5 and tempday <=15):
                self.setpoint = float(
                    self.settings['temp_setpoint_feb_to_may'][0])
                self.day_warm = self.settings['temp_setpoint_feb_to_may'][2]
                self.day_warm_degrees = float(
                    self.settings['temp_setpoint_feb_to_may'][1])

            elif tempmonth == 6 or tempmonth == 7 or (tempmonth ==5 and tempday >15) or (tempmonth ==8 and tempday <=15):
                self.setpoint = float(
                    self.settings['temp_setpoint_may_to_aug'][0])
                self.day_warm = self.settings['temp_setpoint_may_to_aug'][2]
                self.day_warm_degrees = float(
                    self.settings['temp_setpoint_may_to_aug'][1])

            elif tempmonth == 9 or tempmonth == 10 or (tempmonth ==8 and tempday >15) or (tempmonth ==11 and tempday <=15):
                self.setpoint = float(
                    self.settings['temp_setpoint_aug_to_nov'][0])
                self.day_warm = self.settings['temp_setpoint_aug_to_nov'][2]
                self.day_warm_degrees = float(
                    self.settings['temp_setpoint_aug_to_nov'][1])

        else:
            self.setpoint = float(self.settings["temp_setpoint"])
            self.day_warm = float(self.settings['day_warm'])
            self.day_warm_degrees = float(self.settings['day_warm_degrees'])



        # This setpoint can change if there is camera warming during the day etc.
        self.current_setpoint = self.setpoint

        self._set_setpoint(self.setpoint)

        try:
            self.temp_tolerance = float(self.settings["temp_setpoint_tolerance"])
        except:
            self.temp_tolerance = 1.5
            plog("temp tolerance isn't set in obs config, using 1.5 degrees")
        self.protect_camera_from_overheating = float(self.settings['protect_camera_from_overheating'])

        plog("Cooler setpoint is now:  ", self.setpoint)
        pwm = None
        if self.settings["cooler_on"]:  # NB NB why this logic, do we mean if not cooler found on, then turn it on and take the delay?
            self._set_cooler_on()
        if self.theskyx:
            temp, humid, pressure, pwm = self.camera.Temperature, 999.9, 999.9, 0.0
        else:
            temp, humid, pressure , pwm = self._temperature()
        plog("Cooling beginning @:  ", temp, " PWM%:  ", pwm)
        if 1 <= humid <= 100 or 1 <= pressure <= 1100:
            plog("Humidity and pressure:  ", humid, pressure)
        else:
            plog("Camera humidity and pressure is not reported.")

        if self.maxim == True:
            plog("TEC  % load:  ", self._maxim_cooler_power())
        else:
            pass
            #plog("TEC% load is  not reported.")
        if pwm is not None:
            plog("TEC  % load:  ", pwm)

        self.running_an_exposure_set = False
        self.currently_in_smartstack_loop = False

        self.start_time_of_observation = time.time()
        self.current_exposure_time = 20

        self.end_of_last_exposure_time = time.time()
        self.camera_update_reboot = False

        # Initialise variable to a blank array
        self.current_focus_jpg=np.array([])

        # Figure out pixelscale from own observations
        # Or use the config value if there hasn't been enough
        # observations yet.

        try:
            if not self.dummy:
                self.pixelscale_shelf = shelve.open(
                    g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + self.alias + str(g_dev['obs'].name))
                try:
                    pixelscale_list = self.pixelscale_shelf['pixelscale_list']
                    self.pixscale = bn.nanmedian(pixelscale_list)
                    plog('1x1 pixel scale: ' + str(self.pixscale))
                except:
                    pixelscale_list=None
                    self.pixscale = None
                self.pixelscale_shelf.close()


        except:
            plog("ALERT: PIXELSCALE SHELF CORRUPTED. WIPING AND STARTING AGAIN")
            self.pixscale = None
            plog(traceback.format_exc())
            try:
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + self.alias + str(g_dev['obs'].name) + '.dat'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' +
                                'pixelscale' + self.alias + str(g_dev['obs'].name) + '.dat')
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + self.alias + str(g_dev['obs'].name) + '.dir'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' +
                                'pixelscale' + self.alias + str(g_dev['obs'].name) + '.dir')
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'pixelscale' + self.alias + str(g_dev['obs'].name) + '.bak'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' +
                                'pixelscale' + self.alias + str(g_dev['obs'].name) + '.bak')

            except:
                plog(traceback.format_exc())


        # Focus exposure time shelf self-adjustment
        if not self.dummy:
            self.focusexposure_shelf = shelve.open(
                g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'focusexposure' + self.alias + str(g_dev['obs'].name))
            try:
                focusexposure_list = self.focusexposure_shelf['focusexposure_list']
                print ("Focusexposurelist")
                print (focusexposure_list)

                focusarray=np.asarray(focusexposure_list)


                # Get unique exposure times
                # Extract the unique values from the second column
                unique_groups = np.unique(focusarray[:, 1])

                # For each group, compute the median of the corresponding values from column 0
                result = []
                for group in unique_groups:
                    values = focusarray[focusarray[:, 1] == group, 0]
                    median = np.median(values)
                    result.append([median, group])

                result = np.array(result)
                print(result)

                # Update exposure time.

                # Find the index where the median (column 0) is closest to 40
                target = 40
                idx = np.argmin(np.abs(result[:, 0] - target))

                # Report the corresponding group (column 1)
                closest_group = result[idx, 1]
                print(closest_group)

                # Then linearly extrapolate to actually getting 40 targets
                ratio = 40/result[idx,0]
                new_estimated_exposure_time= ratio * closest_group

                g_dev['cam'].focus_exposure=int(max(min(new_estimated_exposure_time,60),25))

                print ("Updated Focus Exposure time: " + str(self.focus_exposure))


            except:
                plog ("No focus exposure shelf so using the config value.")
                plog(traceback.format_exc())
                focusexposure_list=None
                self.focus_exposure = int(self.site_config['focus_exposure_time'])
            self.focusexposure_shelf.close()


        """
        TheSkyX runs on a file mode approach to images rather
        than a direct readout from the camera, so this path
        is set here.
        """
        if self.config["driver"] == "CCDSoft2XAdaptor.ccdsoft5Camera":
            self.camera.AutoSavePath = (
                self.archive_path
                + datetime.strftime(datetime_at_init, "%Y%m%d")
            )
            try:
                os.mkdir(
                    self.archive_path
                    + datetime.strftime(datetime_at_init, "%Y%m%d")
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
        if self.settings["is_cmos"] == True:
            self.is_cmos = True
        else:
            self.is_cmos = False

        if self.settings["dither_enabled"] == True:
            self.dither_enabled = True
        else:
            self.dither_enabled = False

        if self.settings['is_osc'] == True:
            self.is_osc = True
        else:
            self.is_osc = False

        self.camera_model = self.config["desc"]
        # NB We are reading from the actual camera or setting as the case may be. For initial setup,
        # we pull from config for some of the various settings.
        if self.camera is not None:
            try:
                self.camera.BinX = 1
                self.camera.BinY = 1
            except:
                plog("Problem setting up 1x1 binning at startup.")

        self.has_darkslide = False
        self.darkslide_state = "N.A."
        if self.settings["has_darkslide"]:
            self.has_darkslide = True

            self.darkslide_state = 'Unknown'
            self.darkslide_type = self.settings['darkslide_type']

            com_port = self.settings["darkslide_com"]
            self.com_port = com_port
            if self.darkslide_type == 'bistable':
                self.darkslide_instance = Darkslide(com_port)
            # As it takes 12 seconds to open, make sure it is either Open or Shut at startup  NB NB 20250107 Should be closed!!!
            if self.darkslide_state != 'Open':
                if self.darkslide_type is not None:
                    self.darkslide_instance.openDarkslide()
                    self.darkslide_open = True
                    self.darkslide_state = 'Open'
                elif self.darkslide_type == 'ASCOM_FLI_KEPLER':
                    self.camera.Action('SetShutter', 'open')
                    self.darkslide_open = True
                    self.darkslide_state = 'Open'

        self.camera_known_gain = 70000.0      #NB NB 20250112  These numbers make no sense. WE should pull them from obsy-config entries made from MFR specsheets. WER
        self.camera_known_gain_stdev = 70000.0
        self.camera_known_readnoise = 70000.0
        self.camera_known_readnoise_stdev = 70000.0

        try:
            next_seq = next_sequence(self.alias)
        except:
            next_seq = reset_sequence(self.alias)
        self.next_seq = next_seq

        try:

            gain_collector=[]
            stdev_collector=[]


            self.filter_camera_gain_shelf = shelve.open(
                g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'filtercameragain' + self.alias + str(g_dev['obs'].name))

            for entry in self.filter_camera_gain_shelf:
                if entry != 'readnoise':
                    singlentry = self.filter_camera_gain_shelf[entry]
                    gain_collector.append(singlentry[0])
                    stdev_collector.append(singlentry[1])

            if len(gain_collector) > 1:
                while True:
                    print(gain_collector)
                    gainmed = bn.nanmedian(gain_collector)
                    print(gainmed)
                    gainstd = np.nanstd(gain_collector)
                    print(gainstd)
                    new_gain_pile = []
                    new_stdev_pile = []
                    counter = 0
                    for entry in gain_collector:
                        if entry < gainmed + 3 * gainstd:
                            new_gain_pile.append(entry)
                            new_stdev_pile.append(stdev_collector[counter])
                        counter = counter+1
                    if len(new_gain_pile) == len(gain_collector):
                        break
                    if len(new_gain_pile) == 1:
                        self.camera_known_gain = new_gain_pile[0]
                        self.camera_known_gain_stdev = new_gain_pile[0]
                        break
                    gain_collector = copy.deepcopy(new_gain_pile)
                    stdev_collector = copy.deepcopy(new_stdev_pile)
                self.camera_known_gain = gainmed
                self.camera_known_gain_stdev = np.nanstd(gain_collector)
            else:
                self.camera_known_gain = gain_collector[0]
                self.camera_known_gain_stdev = stdev_collector[0]

            singlentry = self.filter_camera_gain_shelf['readnoise']
            self.camera_known_readnoise = (
                singlentry[0] * self.camera_known_gain) / 1.414   #This is debatable. Without the 1.414 it is near the specsheet value for QHY WER 20250112
            self.camera_known_readnoise_stdev = (
                singlentry[1] * self.camera_known_gain) / 1.414
        except:
            plog('failed to estimate gain and readnoise from flats and such')

        plog("Used Camera Gain: " + str(self.camera_known_gain))
        plog("Used Readnoise  : " + str(self.camera_known_readnoise))

        try:
            test_sequence(self.alias)
        except:
            plog("Sequence number failed to load. Starting from zero.")
            plog(traceback.format_exc())
            reset_sequence(self.alias)
        try:
            self._stop_expose()
        except:
            pass

        # Load in previous estimates of readout_time
        try:
            self.readout_shelf = shelve.open(
                g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + self.alias + str(g_dev['obs'].name))
            try:
                readout_list = self.readout_shelf['readout_list']
            except:
                readout_list = []

            self.readout_shelf.close()

            if len(readout_list) > 0:
                self.readout_time = bn.nanmedian(readout_list)
            else:
                # if it is zero, thats fine, it will estimate the readout time on the first readout.
                self.readout_time = 0

            plog("Currently estimated readout time: " + str(self.readout_time))

        except:
            plog("ALERT: READOUT SHELF CORRUPTED. WIPING AND STARTING AGAIN")
            self.pixscale = None
            plog(traceback.format_exc())
            try:
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + self.alias + str(g_dev['obs'].name) + '.dat'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' +
                              'readout' + self.alias + str(g_dev['obs'].name) + '.dat')
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + self.alias + str(g_dev['obs'].name) + '.dir'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' +
                              'readout' + self.alias + str(g_dev['obs'].name) + '.dir')
                if os.path.exists(g_dev['obs'].obsid_path + 'ptr_night_shelf/' + 'readout' + self.alias + str(g_dev['obs'].name) + '.bak'):
                    os.remove(g_dev['obs'].obsid_path + 'ptr_night_shelf/' +
                              'readout' + self.alias + str(g_dev['obs'].name) + '.bak')

            except:
                plog(traceback.format_exc())


        # OVERSCAN SETUP
        # Camera overscan values
        self.overscan_values={}
        self.overscan_values['QHY600']=[0,38,32,0]
        self.overscan_values['QHY268']=[0,34,24,4] #dunno , top, left, dunno (according to fits liberator)
        self.overscan_values['QHY461']=[2,2,50,50]
        self.overscan_values['SBIG16803']=[0,0,0,0]

        self.overscan_values['asi1600']=[0,0,0,0]
        self.overscan_values['none']=[0,0,0,0]


        self.overscan_left=self.overscan_values[site_config["camera"][self.name]['overscan_trim']][0]
        self.overscan_right=self.overscan_values[site_config["camera"][self.name]['overscan_trim']][1]
        self.overscan_up=self.overscan_values[site_config["camera"][self.name]['overscan_trim']][2]
        self.overscan_down=self.overscan_values[site_config["camera"][self.name]['overscan_trim']][3]


        # The skyx needs its own separate camera update thread to do with some theskyx
        # curiosities and also the win32com sorta connection it makes.

        if self.theskyx:
            self.theskyx_set_cooler_on = True
            self.theskyx_cooleron = True
            self.theskyx_set_setpoint_trigger = True
            self.theskyx_set_setpoint_value = self.setpoint
            self.theskyx_temperature = self.camera.Temperature, 999.9, 999.9, 0
            self.camera_update_period = 5
            self.camera_update_timer = time.time() - 2 * self.camera_update_period
            self.camera_updates = 0
            self.camera_update_thread = threading.Thread(
                target=self.camera_update_thread)
            self.camera_update_thread.daemon = True
            self.camera_update_thread.start()

    def __repr__(self):
        return f"<Camera {self.name} (Role: {self.role})>"

    def openDarkslide(self):

        if self.darkslide_state != 'Open':
            if self.darkslide_type is not None:

                opened = self.darkslide_instance.openDarkslide()
            elif self.darkslide_type == 'ASCOM_FLI_SHUTTER':
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
                closed = self.darkslide_instance.closeDarkslide()
            elif self.darkslide_type == 'ASCOM_FLI_Kepler':  # NB NB this logic is faulty wer
                self.camera.Action('SetShutter', 'close')
            if closed:
                self.darkslide_open = False
                self.darkslide_state = 'Closed'
                return False
            else:
                return True

    def camera_update_thread(self):

        win32com.client.pythoncom.CoInitialize()

        self.camera_update_wincom = win32com.client.Dispatch(self.driver)

        self.camera_update_wincom.Connect()

        # This stopping mechanism allows for threads to close cleanly.
        while True:

            # update every so often, but update rapidly if slewing.
            if (self.camera_update_timer < time.time() - self.camera_update_period) and not self.updates_paused:

                if self.camera_update_reboot:
                    win32com.client.pythoncom.CoInitialize()
                    self.camera_update_wincom = win32com.client.Dispatch(
                        self.driver)

                    self.camera_update_wincom.Connect()

                    self.updates_paused = False
                    self.camera_update_reboot = False

                try:
                    self.theskyx_temperature = self.camera_update_wincom.Temperature, 999.9, 999.9, 0

                    self.theskyx_cooleron = self.camera_update_wincom.RegulateTemperature

                    if self.theskyx_set_cooler_on == True:

                        self.camera_update_wincom.RegulateTemperature = 1
                        self.theskyx_set_cooler_on = False

                    if self.theskyx_set_setpoint_trigger == True:
                        self.camera_update_wincom.TemperatureSetpoint = float(
                            self.theskyx_set_setpoint_value)
                        self.camera_update_wincom.RegulateTemperature = 1
                        self.current_setpoint = self.theskyx_set_setpoint_value
                        self.theskyx_set_setpoint_trigger = False

                    if self.theskyx_abort_exposure_trigger == True:
                        self.camera_update_wincom.Abort()
                        self.theskyx_abort_exposure_trigger = False
                except:
                    plog("non-permanent glitch out in the camera thread.")
                    plog(traceback.format_exc())

                time.sleep(max(1, self.camera_update_period))
            else:
                time.sleep(max(1, self.camera_update_period))


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
        return self.theskyx_temperature

    def _theskyx_cooler_power(self):
        return self.camera.CoolerPower

    def _theskyx_heatsink_temp(self):
        return self.camera.HeatSinkTemperature

    def _theskyx_cooler_on(self):
        return self.theskyx_cooleron

    def _theskyx_set_cooler_on(self):
        self.theskyx_set_cooler_on = True
        return True

    def _theskyx_set_setpoint(self, p_temp):

        self.theskyx_set_setpoint_trigger = True
        self.theskyx_set_setpoint_value = float(p_temp)
        self.current_setpoint = float(p_temp)
        return float(p_temp)

    def _theskyx_setpoint(self):
        return self.theskyx_set_setpoint_value

    def theskyx_async_expose(self):
        self.async_exposure_lock = True
        tempcamera = win32com.client.Dispatch(self.driver)
        tempcamera.Connect()
        timeout_timer=time.time()

        while not tempcamera.IsExposureComplete and (time.time() - timeout_timer) < (self.theskyxExposureTime + self.readout_time):
            self.theskyxIsExposureComplete = False
            plog("waiting for skyx exposure complete.")
            time.sleep(0.01)
        tempcamera.ExposureTime = self.theskyxExposureTime
        tempcamera.Frame = self.theskyxFrame

        try:
            tempcamera.TakeImage()
        except:
            if 'Process aborted.' in str(traceback.format_exc()):
                plog(
                    "Image aborted. This functioning is ok. Traceback just for checks that it is working.")
                self.theskyxIsExposureComplete = True
                self.async_exposure_lock = False
                return
            elif 'SBIG driver' in str(traceback.format_exc()):
                plog(traceback.format_exc())
                plog(
                    "Killing and rebooting TheSKYx and seeing if it will continue on after SBIG fail")
                g_dev['obs'].kill_and_reboot_theskyx(
                    g_dev['mnt'].return_right_ascension(), g_dev['mnt'].return_declination())
                self.theskyxIsExposureComplete = True
                self.async_exposure_lock = False
                return
            else:
                plog(traceback.format_exc())
                plog("MTF hunting this error")
                self.theskyxIsExposureComplete = True
                self.async_exposure_lock = False
                return

        timeout_timer = time.time()
        while not tempcamera.IsExposureComplete and (time.time() - timeout_timer) < (self.theskyxExposureTime + self.readout_time):
            self.theskyxIsExposureComplete = False
            time.sleep(0.01)

        # If that was overly long a wait then cancel exposure
        if (time.time() - timeout_timer) > 2 * (self.theskyxExposureTime + self.readout_time):
            plog("That was a very long readout for the image.... " +
                 str((time.time() - timeout_timer)))

        self.theskyxIsExposureComplete = True
        self.theskyxLastImageFileName = tempcamera.LastImageFileName
        tempcamera.ShutDownTemperatureRegulationOnDisconnect = False
        self.async_exposure_lock = False

    def _theskyx_expose(self, exposure_time, bias_dark_or_light_type_frame):
        self.theskyxExposureTime = exposure_time
        if bias_dark_or_light_type_frame == 'dark' and not self.settings['cmos_on_theskyx'] :
            self.theskyxFrame = 3
        elif bias_dark_or_light_type_frame == 'bias' and not self.settings['cmos_on_theskyx'] :
            self.theskyxFrame = 2
        else:
            self.theskyxFrame = 1
        self.theskyxIsExposureComplete = False
        thread = threading.Thread(target=self.theskyx_async_expose)
        thread.daemon = True
        thread.start()

    def _theskyx_stop_expose(self):
        try:
            self.theskyx_abort_exposure_trigger = True
        except:
            plog(traceback.format_exc())
        self.expresult = {}
        self.expresult["stopped"] = True
        return

    def _theskyx_imageavailable(self):
        try:
            return self.theskyxIsExposureComplete
        except:
            if 'Process aborted.' in str(traceback.format_exc()):
                plog("Image isn't available because the command was aborted.")
            else:
                plog(traceback.format_exc())

    def _theskyx_getImageArray(self):

        # Wait for it to turn up....
        file_wait_timer = time.time()
        while not os.path.exists(self.theskyxLastImageFileName):
            if time.time()-file_wait_timer > 15:
                plog("Waiting for file to arrive for 15 seconds but it never did: " +
                     str(self.theskyxLastImageFileName))
                return None
            time.sleep(0.05)

        # Make sure it is openable - can happen if the file appears but it hasn't fully written yet
        file_wait_timer = time.time()
        while True:
            try:
                imageTempOpen=fits.open(self.theskyxLastImageFileName, uint=False)[0].data.astype("float32")
                # Do overscan
                imageTempOpen=imageTempOpen[ self.overscan_left: self.imagesize_x-self.overscan_right, self.overscan_up: self.imagesize_y- self.overscan_down  ]

                break
            except:
                if time.time()-file_wait_timer > 15:
                    plog("Waiting for file to become big for 15 seconds but it never did: " +
                         str(self.theskyxLastImageFileName))
                    return None
                time.sleep(0.05)
        try:
            os.remove(self.theskyxLastImageFileName)
        except Exception as e:
            plog("Could not remove theskyx image file: ", e)
        return imageTempOpen


    def _dummy_connected(self):
        return True

    def _dummy_connect(self, p_connect):
        #self.camera.LinkEnabled = p_connect
        return True

    def _dummy_temperature(self):
        return 5.0, 999.9, 999.9,0

    def _dummy_cooler_power(self):
        return 50.0

    def _dummy_heatsink_temp(self):
        return 5.0

    def _dummy_cooler_on(self):
        return (
            True
        )

    def _dummy_set_cooler_on(self):
        #self.camera.CoolerOn = True
        return (
            True
        )

    def _dummy_set_setpoint(self, p_temp):
        #self.camera.TemperatureSetpoint = float(p_temp)
        #self.current_setpoint = p_temp
        return 5.0

    def _dummy_setpoint(self):
        return 5.0

    def _dummy_expose(self, exposure_time, bias_dark_or_light_type_frame):
        # if bias_dark_or_light_type_frame == 'bias' or bias_dark_or_light_type_frame == 'dark':
        #     imtypeb = 0
        # else:
        #     imtypeb = 1
        # self.camera.Expose(exposure_time, imtypeb)
        plog ("dummy got asked to exposure")

    def _dummy_stop_expose(self):
        # self.camera.AbortExposure()
        plog ("dummy got asked to abort")
        self.expresult = {}
        self.expresult["stopped"] = True

    def _dummy_imageavailable(self):
        return True

    def _dummy_getImageArray(self):


        ra=g_dev['mnt'].right_ascension_directly_from_mount * 15
        dec=g_dev['mnt'].declination_directly_from_mount

        cutout_size = 30 / 60  # Convert 30 arcminutes to degrees

        # Create a SkyCoord object for the center
        center = SkyCoord(ra=ra, dec=dec, unit=(u.deg, u.deg))

        # Query APASS catalog from Vizier
        Vizier.ROW_LIMIT = -1  # Remove row limit to get all results
        catalogs = Vizier.query_region(
            center,
            radius=cutout_size * u.deg,
            catalog="II/336"  # APASS DR9 catalog ID in Vizier
        )

        # Check if data is available
        if "II/336/apass9" in catalogs.keys():
            apass_data = catalogs["II/336/apass9"]
            # Select columns of interest
            stars = apass_data[['RAJ2000', 'DEJ2000', 'Vmag']]
            #print(stars)
        else:
            print("No data found in the APASS catalog for the given region.")



        # Parameters
        image_size = (2400, 2400)  # Image size (width, height)
        pixel_scale = 0.75  # Pixel scale in arcseconds/pixel
        ra_center = ra  # RA of the image center in degrees
        dec_center = dec   # Dec of the image center in degrees

        star_positions=[]
        for star in stars:
            if '-' not in str(star[2]):
                star_positions.append((star[0],star[1],star[2]))

        # Convert star positions to SkyCoord
        center_coord = SkyCoord(ra=ra_center, dec=dec_center, unit=(u.deg, u.deg))
        star_coords = SkyCoord(ra=[pos[0] for pos in star_positions],
                               dec=[pos[1] for pos in star_positions],
                               unit=(u.deg, u.deg))

        # Calculate offsets in arcseconds
        ra_offset = (star_coords.ra - center_coord.ra).to(u.arcsec)
        dec_offset = (star_coords.dec - center_coord.dec).to(u.arcsec)

        # Convert offsets to pixels
        x_pixels = (ra_offset / pixel_scale).value + image_size[0] / 2
        y_pixels = (dec_offset / pixel_scale).value + image_size[1] / 2

        # Combine x and y pixel locations and fluxes
        pixel_positions = np.column_stack((x_pixels, y_pixels, np.asarray(star_positions)[:,2]))

        # Print results
        # print("Star positions in pixel coordinates (x, y):")
        # print(pixel_positions)

        xpixelsize = 2400
        ypixelsize = 2400

        # Make blank synthetic image with a sky background
        synthetic_image = np.zeros([xpixelsize, ypixelsize]) + 100

        # Add in noise to background as well
        synthetic_image = synthetic_image + np.random.normal(loc=100,
                                        scale=10,
                                        size=synthetic_image.shape)

        # Create the PSF kernel
        fwhm = 5
        psf = create_gaussian_psf(fwhm, size=21)

        # Add each star to the image
        for starstat in pixel_positions:
            if starstat[0] > 50 and starstat[0] < 2350:
                if starstat[1] > 50 and starstat[1] < 2350:
                    try:
                        add_star_with_psf(synthetic_image, int(starstat[0]), int( starstat[1]),  int(pow(10,-0.4 * (starstat[2] -23))), psf)
                    except:
                        plog(traceback.format_exc())


        return synthetic_image

    def _zwo_connected(self):
        return True

    def _zwo_connect(self, p_connect):
        #self.camera.LinkEnabled = p_connect
        return True

    def _zwo_temperature(self):

        return float(zwocamera.get_control_value(asi.ASI_TEMPERATURE)[0])/10, 0,0, zwocamera.get_control_value(asi.ASI_COOLER_POWER_PERC)[0]

    def _zwo_cooler_power(self):
        return float(zwocamera.get_control_value(asi.ASI_COOLER_POWER_PERC)[0])

    def _zwo_cooler_on(self):
        zwocamera.set_control_value(asi.ASI_COOLER_ON, True)
        return zwocamera.get_control_value(asi.ASI_COOLER_ON)

    def _zwo_set_cooler_on(self):
        #self.camera.CoolerOn = True
        return  True

    def _zwo_set_setpoint(self, p_temp):
        zwocamera.set_control_value(asi.ASI_TARGET_TEMP, int(p_temp))

        return p_temp

    def _zwo_setpoint(self):
        return self.camera.TemperatureSetpoint

    def _zwo_stop_expose(self):
        # self.camera.AbortExposure()
        # self.expresult = {}
        # self.expresult["stopped"] = True
        print ("Stop expose not implemented")

    def _zwo_imageavailable(self):
        if zwocamera.get_exposure_status() == 1:
            return False
        else:
            return True

    def _zwo_expose(self, exposure_time, bias_dark_or_light_type_frame):

        self.substacker_available = False

        if bias_dark_or_light_type_frame == 'bias':
            exposure_time = 40 / 1000/1000  # shortest requestable exposure time

        if not self.substacker:
            zwocamera.set_control_value(asi.ASI_EXPOSURE, int(exposure_time * 1000 * 1000))  # Convert to microseconds
            zwocamera.start_exposure()

        else:

            if self.current_filter==None:
                self.current_filter='none'

            # Boost Narrowband and low throughput
            if self.current_filter.lower() in ["u", "ju", "bu", "up", "z", "zs", "zp", "ha", "h", "o3", "o", "s2", "s", "cr", "c", "n2", "n"]:
                exp_of_substacks = 30
                N_of_substacks = int((exposure_time / exp_of_substacks))
            else:
                exp_of_substacks = 10
                N_of_substacks = int(exposure_time / exp_of_substacks)

            self.substacker_filenames = []
            base_tempfile = str(time.time()).replace(".", "")
            for i in range(N_of_substacks):
                self.substacker_filenames.append(
                    self.local_calibration_path + "smartstacks/" + base_tempfile + str(i) + ".npy")

            thread = threading.Thread(target=self.zwo_substacker_thread, args=(
                exp_of_substacks, N_of_substacks, exp_of_substacks, copy.deepcopy(self.substacker_filenames),))
            thread.daemon = True
            thread.start()


    def zwo_substacker_thread(self, exposure_time, N_of_substacks, exp_of_substacks, substacker_filenames):

        self.substacker_available = False
        readout_estimate_holder=[]
        self.sub_stacker_midpoints=[]


        for subexposure in range(N_of_substacks):
            # Check there hasn't been a cancel sent through
            if g_dev["obs"].stop_all_activity:
                plog("stop_all_activity cancelling out of camera exposure")
                self.shutter_open = False
                return
            if g_dev["obs"].exposure_halted_indicator:
                self.shutter_open = False
                return

            plog("Collecting subexposure " + str(subexposure+1))

            zwocamera.set_control_value(asi.ASI_EXPOSURE, int(exposure_time * 1000 * 1000))  # Convert to microseconds


            if subexposure == 0:
                self.substack_start_time = time.time()
            self.expected_endpoint_of_substack_exposure = time.time() + exp_of_substacks
            self.sub_stacker_midpoints.append(copy.deepcopy(time.time() + (0.5*exp_of_substacks)))
            zwocamera.start_exposure()
            exposure_timer = time.time()

            # save out previous array to disk during exposure
            if subexposure > 0:
                if not (self.overscan_down == 0 and self.overscan_up == 0 and self.overscan_left == 0 and self.overscan_right==0):
                    try:
                        image = image[self.overscan_left: self.imagesize_x-self.overscan_right,self.overscan_up: self.imagesize_y - self.overscan_down]
                    except:
                        plog(traceback.format_exc())
                np.save(substacker_filenames[subexposure-1], image)

            while (time.time() - exposure_timer) < exp_of_substacks:
                time.sleep(0.001)

            # If this is the last exposure of the set of subexposures, then report shutter closed
            if subexposure == (N_of_substacks-1):
                self.shutter_open = False

            while zwocamera.get_exposure_status() == 1:
                time.sleep(0.05)

            time_before_last_substack_readout = time.time()
            try:
                image = zwocamera.get_data_after_exposure()

                image=np.frombuffer(image, dtype=np.uint16).reshape(self.imagesize_y,self.imagesize_x)

                time_after_last_substack_readout = time.time()

                readout_estimate_holder.append(time_after_last_substack_readout - time_before_last_substack_readout)

                # If it is the last file in the substack, throw it out to the slow process queue to save
                # So that the camera can get started up again quicker.
                if subexposure == (N_of_substacks - 1):
                    #tempsend= np.reshape(image[0:(self.imagesize_x*self.imagesize_y)], (self.imagesize_x, self.imagesize_y))
                    if not (self.overscan_down == 0 and self.overscan_up == 0 and self.overscan_left == 0 and self.overscan_right==0):
                        image=image[ self.overscan_left: self.imagesize_x-self.overscan_right, self.overscan_up: self.imagesize_y- self.overscan_down  ]
                    np.save(substacker_filenames[subexposure],image)

            except:
                plog ("ZWO READOUT ERROR. Probably a timeout?")
                plog(traceback.format_exc())
                image=np.asarray([])
                np.save(substacker_filenames[subexposure],image)

        self.readout_estimate= np.median(np.array(readout_estimate_holder))
        self.substacker_available=True
        self.shutter_open=False

    def _zwo_getImageArray(self):

        if self.substacker:
            return 'substack_array'
        else:

            try:
                frame = zwocamera.get_data_after_exposure()

                return np.frombuffer(frame, dtype=np.uint16).reshape(self.imagesize_y,self.imagesize_x)
            except:
                plog ("ZWO READOUT ERROR. Probably a timeout?")
                plog(traceback.format_exc())
                return np.asarray([])

    def _maxim_connected(self):
        return self.camera.LinkEnabled

    def _maxim_connect(self, p_connect):
        self.camera.LinkEnabled = p_connect
        return self.camera.LinkEnabled

    def _maxim_temperature(self):
        return self.camera.Temperature, 999.9, 999.9,0

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
            imtypeb = 0
        else:
            imtypeb = 1
        self.camera.Expose(exposure_time, imtypeb)

    def _maxim_stop_expose(self):
        self.camera.AbortExposure()
        self.expresult = {}
        self.expresult["stopped"] = True

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
            temptemp = self.camera.CCDTemperature
        except:
            plog("failed at getting the CCD temperature")
            temptemp = 999.9
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
            imtypeb = 0
        else:
            imtypeb = 1

        self.camera.StartExposure(exposure_time, imtypeb)

    def _ascom_stop_expose(self):
        self.camera.StopExposure()  # ASCOM also has an AbortExposure method.
        self.expresult = {}
        self.expresult["stopped"] = True

    def _ascom_getImageArray(self):
        return np.asarray(self.camera.ImageArray)

    def _qhyccd_connected(self):
        print("MTF still has to connect QHY stuff")
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

            temptemp = qhycam.so.GetQHYCCDParam(
                qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP)
            humidity = qhycam.so.GetQHYCCDParam(
                qhycam.camera_params[qhycam_id]['handle'], qhycam.CAM_HUMIDITY)
            pressure = qhycam.so.GetQHYCCDParam(
                qhycam.camera_params[qhycam_id]['handle'], qhycam.CAM_PRESSURE)
            pwm = qhycam.so.GetQHYCCDParam(
                qhycam.camera_params[qhycam_id]['handle'],     qhycam.CONTROL_CURPWM)
            manual_pwm = qhycam.so.GetQHYCCDParam(
                qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_MANULPWM)
            self.pwm_percent = " "+str(int(pwm*100.0/255))+"%"
            self.spt_C = " "+str(round(self.current_setpoint,1))+"C"
            self.temp_C = " "+str(round(temptemp, 1))+"C"
            self.hum_percent = " "+str(int(humidity))+"%"

        except:
            print("failed at getting the CCD temperature, humidity or pressure.")
            temptemp = 999.9

        return temptemp, humidity, pressure, round(pwm*100.0/255,1)

    def _qhyccd_cooler_on(self):
        # print ("QHY DOESN'T HAVE AN IS COOLER ON METHOD)
        return True

    def _qhyccd_set_cooler_on(self):
        temptemp = qhycam.so.SetQHYCCDParam(
            qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_COOLER, c_double(self.current_setpoint))
        return True

    def _qhyccd_set_setpoint(self, p_temp):
        temptemp = qhycam.so.SetQHYCCDParam(
            qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_COOLER, c_double(p_temp))
        self.current_setpoint = p_temp
        return p_temp

    def _qhyccd_setpoint(self):
        try:
            temptemp = qhycam.so.GetQHYCCDParam(
                qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_CURTEMP)
        except:
            print("failed at getting the CCD temperature")
            temptemp = 999.9
        return temptemp

    def qhy_substacker_thread(self, exposure_time, N_of_substacks, exp_of_substacks, substacker_filenames):

        self.substacker_available = False
        readout_estimate_holder=[]
        self.sub_stacker_midpoints=[]


        for subexposure in range(N_of_substacks):
            # Check there hasn't been a cancel sent through
            if g_dev["obs"].stop_all_activity:
                plog("stop_all_activity cancelling out of camera exposure")
                self.shutter_open = False
                return
            if g_dev["obs"].exposure_halted_indicator:
                self.shutter_open = False
                return

            plog("Collecting subexposure " + str(subexposure+1))

            qhycam.so.SetQHYCCDParam(qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(
                exp_of_substacks*1000*1000))
            if subexposure == 0:
                self.substack_start_time = time.time()
            self.expected_endpoint_of_substack_exposure = time.time() + exp_of_substacks
            self.sub_stacker_midpoints.append(copy.deepcopy(time.time() + (0.5*exp_of_substacks)))
            qhycam.so.ExpQHYCCDSingleFrame(
                qhycam.camera_params[qhycam_id]['handle'])
            exposure_timer = time.time()

            # save out previous array to disk during exposure
            if subexposure > 0:
                tempsend = np.reshape(
                    image[0:(self.imagesize_x*self.imagesize_y)], (self.imagesize_x, self.imagesize_y))

                #tempsend=tempsend[ 0:6384, 32:9600]
                tempsend = tempsend[self.overscan_left: self.imagesize_x-self.overscan_right,
                                    self.overscan_up: self.imagesize_y - self.overscan_down]

                np.save(substacker_filenames[subexposure-1], tempsend)

            while (time.time() - exposure_timer) < exp_of_substacks:
                time.sleep(0.001)

            # If this is the last exposure of the set of subexposures, then report shutter closed
            if subexposure == (N_of_substacks-1):
                self.shutter_open = False

            # READOUT FROM THE QHY
            image_width_byref = c_uint32()
            image_height_byref = c_uint32()
            bits_per_pixel_byref = c_uint32()
            time_before_last_substack_readout = time.time()
            success = qhycam.so.GetQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'],
                                                     byref(image_width_byref),
                                                     byref(image_height_byref),
                                                     byref(
                                                         bits_per_pixel_byref),
                                                     byref(
                                                         qhycam.camera_params[qhycam_id]['channels']),
                                                     byref(qhycam.camera_params[qhycam_id]['prev_img_data']))

            image = np.ctypeslib.as_array(
                qhycam.camera_params[qhycam_id]['prev_img_data'])
            time_after_last_substack_readout = time.time()

            readout_estimate_holder.append(time_after_last_substack_readout - time_before_last_substack_readout)

            # If it is the last file in the substack, throw it out to the slow process queue to save
            # So that the camera can get started up again quicker.
            if subexposure == (N_of_substacks -1 ):
                tempsend= np.reshape(image[0:(self.imagesize_x*self.imagesize_y)], (self.imagesize_x, self.imagesize_y))
                tempsend=tempsend[ self.overscan_left: self.imagesize_x-self.overscan_right, self.overscan_up: self.imagesize_y- self.overscan_down  ]
                np.save(substacker_filenames[subexposure],tempsend)

        self.readout_estimate= np.median(np.array(readout_estimate_holder))
        self.substacker_available=True
        self.shutter_open=False


    def _qhyccd_expose(self, exposure_time, bias_dark_or_light_type_frame):

        self.substacker_available = False

        if bias_dark_or_light_type_frame == 'bias':
            exposure_time = 40 / 1000/1000  # shortest requestable exposure time

        if not self.substacker:
            qhycam.so.SetQHYCCDParam(
                qhycam.camera_params[qhycam_id]['handle'], qhycam.CONTROL_EXPOSURE, c_double(exposure_time*1000*1000))
            qhycam.so.ExpQHYCCDSingleFrame(
                qhycam.camera_params[qhycam_id]['handle'])  #This is the place for an exposure!
        else:


            # Boost Narrowband and low throughput broadband
            if not self.current_filter == None:
                if self.current_filter.lower() in ["u", "ju", "bu", "up", "z", "zs", "zp", "ha", "h", "o3", "o", "s2", "s", "cr", "c", "n2", "n"]:
                    exp_of_substacks = 30
                    N_of_substacks = int((exposure_time / exp_of_substacks))
                else:
                    exp_of_substacks = 10
                    N_of_substacks = int(exposure_time / exp_of_substacks)
            else:
                exp_of_substacks = 10
                N_of_substacks = int(exposure_time / exp_of_substacks)


            self.substacker_filenames = []
            base_tempfile = str(time.time()).replace(".", "")
            for i in range(N_of_substacks):
                self.substacker_filenames.append(
                    self.local_calibration_path + "smartstacks/" + base_tempfile + str(i) + ".npy")
            #This thread executes a substacks
            thread = threading.Thread(target=self.qhy_substacker_thread, args=(
                exp_of_substacks, N_of_substacks, exp_of_substacks, copy.deepcopy(self.substacker_filenames),))
            thread.daemon = True
            thread.start()

    def _qhyccd_stop_expose(self):
        expresult = {}
        expresult["stopped"] = True
        self.shutter_open = False
        try:
            qhycam.so.CancelQHYCCDExposingAndReadout(
                qhycam.camera_params[qhycam_id]['handle'])
        except:
            plog(traceback.format_exc())

    def _qhyccd_getImageArray(self):

        if self.substacker:
            return 'substack_array'
        else:
            image_width_byref = c_uint32()
            image_height_byref = c_uint32()
            bits_per_pixel_byref = c_uint32()
            time_before_readout=time.time()
            success = qhycam.so.GetQHYCCDSingleFrame(qhycam.camera_params[qhycam_id]['handle'],
                                                     byref(image_width_byref),
                                                     byref(image_height_byref),
                                                     byref(
                                                         bits_per_pixel_byref),
                                                     byref(
                                                         qhycam.camera_params[qhycam_id]['channels']),
                                                     byref(qhycam.camera_params[qhycam_id]['prev_img_data']))
            image = np.ctypeslib.as_array(qhycam.camera_params[qhycam_id]['prev_img_data'])
            time_after_readout=time.time()
            self.readout_estimate= time_after_readout - time_before_readout
            tempsend= np.reshape(image[0:(self.imagesize_x*self.imagesize_y)], (self.imagesize_x, self.imagesize_y))
            tempsend=tempsend[ self.overscan_left: self.imagesize_x-self.overscan_right, self.overscan_up: self.imagesize_y- self.overscan_down  ]
            return tempsend
# =============================================================================
    # def create_simple_autosave(
    #     self,
    #     exp_time=0,
    #     img_type=0,
    #     speed=0,
    #     suffix="",
    #     repeat=1,
    #     readout_mode="Normal",
    #     filter_name="W",
    #     enabled=1,
    #     column=1,
    # ):
#
#         # Creates a valid Maxium Autosave file.   THIS IS OBSOLETE CODE
#         exp_time = round(abs(float(exp_time)), 3)
#         if img_type > 3:
#             img_type = 0
#         repeat = abs(int(repeat))
#         if repeat < 1:
#             repeat = 1
#         binning = abs(int(1))
#         if filter_name == "":
#             filter_name = "w"
#         proto_file = open(self.camera_path + "seq/ptr_proto.seq")
#         proto = proto_file.readlines()
#         proto_file.close()
#
#         if column == 1:
#             proto[51] = proto[51][:9] + str(img_type) + proto[51][10:]
#             proto[50] = proto[50][:9] + str(exp_time) + proto[50][12:]
#             proto[48] = proto[48][:12] + str(suffix) + proto[48][12:]
#             proto[47] = proto[47][:10] + str(speed) + proto[47][11:]
#             proto[31] = proto[31][:11] + str(repeat) + proto[31][12:]
#             proto[29] = proto[29][:17] + readout_mode + proto[29][23:]
#             proto[13] = proto[13][:12] + filter_name + proto[13][13:]
#             proto[10] = proto[10][:12] + str(enabled) + proto[10][13:]
#             proto[1] = proto[1][:12] + str(binning) + proto[1][13:]
#         seq_file = open(self.camera_path + "seq/ptr_mrc.seq", "w")
#
#         for item in range(len(proto)):
#             seq_file.write(proto[item])
#         seq_file.close()
# =============================================================================

    def get_status(self):
        status = {}
        status["active_camera"] = self.name
        if self.settings["has_darkslide"]:
            status["darkslide"] = self.darkslide_state
        else:
            status["darkslide"] = "unknown"


        try:
            cam_stat = self.alias + \
                ", S " + self.spt_C + \
                ", T " + self.temp_C + \
                ", P " + self.pwm_percent + \
                ", H " + self.hum_percent +\
                ", A " + str(round(g_dev['foc'].current_focus_temperature, 1))
        except:
            cam_stat = 'status_failed'
        status[
            "status"
        ] = cam_stat  # The state could be expanded to be more meaningful. for instance report TEC % TEmp, temp setpoint...
        return status



    def parse_command(self, command):

        req = command["required_params"]
        opt = command["optional_params"]
        action = command["action"]
        self.user_id = command["user_id"]
        if self.user_id != self.last_user_id:
            self.last_user_id = self.user_id
        self.user_name = command["user_name"]

        if ("object_name" in opt):
            if opt["object_name"] == "":
                opt["object_name"] = "Unspecified"
                plog("Target Name:  ", opt["object_name"])
            else:
                plog("Target Name:  ", opt["object_name"])
        if self.user_name != self.last_user_name:
            self.last_user_name = self.user_name
        if action == "expose":  # and not self.running_an_exposure_set:

            "First we parse the hint"   #******I think this may be obsolete WER 20250607
            if 'hint' in opt and len(opt['hint']) > 0:
                plog("hint:  ", opt['hint'])
                hint = opt['hint'].split(";")
                for item in hint:
                    term, chg = item.split("=")
                    term = term.strip(' ')
                    if term in ['refr', 'modl', 'rate', 'drft']:
                        if term == 'modl':
                            g_dev['mnt'].model_on = bool(chg)
                        if term == 'refr':
                            g_dev['mnt'].refr_on = bool(chg)
                        if term == 'rate':
                            g_dev['mnt'].rates_on = bool(chg)
                        if term == 'drft':
                            g_dev['mnt'].drift_on = bool(chg)

                    else:
                        if chg[0] == '+':  #Increment
                            g_dev['mnt'].model[term] += math.radians(float(chg[1:])/3600.)
                        elif chg[0:2] == '--':  #Decrement
                            g_dev['mnt'].model[term] -= math.radians(float(chg[2:])/3600.)
                        else:  #Assign value
                            g_dev['mnt'].model[term] = math.radians(float(chg)/3600.)
                        print(' R, M, model:  ', g_dev['mnt'].refr_on, g_dev['mnt'].model_on, g_dev['mnt'].model)
                pass

            if self.running_an_exposure_set:
                plog(
                    "Cannot expose, camera is currently busy, waiting for exposures to clear")
                dont_wait_forever = time.time()
                while True:
                    if (time.time()-dont_wait_forever) > 5:   #Why this 5 second timeout? What is this routine for?
                        plog("Exposure too busy for too long, returning")
                        return
                    if self.running_an_exposure_set:
                        time.sleep(0.1)
                    else:
                        break
            if req['image_type'].lower() in (
                "bias",
                "dark",
                "screenflat",
                "skyflat",
                "nearflat",
                "thorflat",
                "arcflat",
                "lampflat",
                "solarflat",
            ):
                manually_requested_calibration = True
            else:
                manually_requested_calibration = False

            reported=False
            while g_dev['seq'].currently_running_centering:
                if not reported:
                    plog ("waiting for centering to finish")
                    reported=True
                time.sleep(0.1)

            g_dev['obs'].report_to_nightlog("Individual Exposure Commanded: " + str(command))

            self.expose_command(req, opt, user_id=command['user_id'], user_name=command['user_name'],
                                manually_requested_calibration=manually_requested_calibration)

            self.active_script = None

        elif action == "darkslide_close":

            if self.darkslide_type == 'bistable':
                g_dev["drk"].closeDarkslide()
            elif self.darkslide_type == 'ASCOM_FLI_SHUTTER':
                self.camera.Action('SetShutter', 'close')
            plog("Closing the darkslide.")
            self.darkslide_state = 'Closed'
        elif action == "darkslide_open":

            if self.darkslide_type == 'bistable':
                g_dev["drk"].openDarkslide()
            elif self.darkslide_type == 'ASCOM_FLI_SHUTTER':
                self.camera.Action('SetShutter', 'open')
            plog("Opening the darkslide.")
            self.darkslide_state = 'Open'
        elif action == "stop":
            self.stop_command(req, opt)
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
            solve_it=False,
            calendar_event_id=None,
            skip_open_check=False,
            skip_daytime_check=False,
            manually_requested_calibration=False,
            useastrometrynet=False,
            upload_metadata={},
            filterwheel_device=None
        ):

        # We've had multiple cases of multiple camera exposures trying to go at once
        # And it is likely because it takes a non-zero time to get to Phase II
        # So even in the setup phase the "exposure" is "busy"
        self.running_an_exposure_set = True

        # Make sure these are reset to standard values
        g_dev['obs'].stop_all_activity = False
        g_dev['obs'].exposure_halted_indicator = False

        # Parse inputs from required_params and optional_params
        #
        # Note that required_params and optional_params are passed into some
        # subprocess functions too, so just because a value isn't defined here
        # doesn't mean it's never used.
        exposure_time = float(required_params.get("time", 1.0))
        imtype = required_params.get("image_type", "light")
        smartstack = required_params.get('smartstack', True)   #Consider making this an attribute as in smartstacker   WER
        self.substacker = required_params.get('substack', True)

        count = int(optional_params.get("count", 1))
        if count < 1:
            count = 1  # Hence frame does not repeat unless count > 1
        zoom_factor = optional_params.get('zoom', "Full")

        # First check that it isn't an exposure that doesn't need a check (e.g. bias, darks etc.)
        if not g_dev['obs'].assume_roof_open and not skip_open_check and not g_dev['obs'].scope_in_manual_mode:
            # Second check, if we are not open and available to observe, then .... don't observe!
            if g_dev['obs'].open_and_enabled_to_observe == False:
                g_dev['obs'].send_to_user(
                    "Refusing exposure request as the observatory is not enabled to observe.")
                plog(
                    "Refusing exposure request as the observatory is not enabled to observe.")
                self.running_an_exposure_set = False
                return


        # Third check, check it isn't daytime and institute maximum exposure time
        # Unless it is a command from the sequencer flat_scripts or a requested calibration frame
        skip_daytime_check = True      #WERexplore
        skip_calibration_check = False

        if imtype.lower() in ['fortymicrosecond_exposure_dark', 'fourhundredmicrosecond_exposure_dark','pointzerozerofourfive_exposure_dark', 'onepointfivepercent_exposure_dark', 'fivepercent_exposure_dark', 'tenpercent_exposure_dark', 'quartersec_exposure_dark', 'halfsec_exposure_dark', 'threequartersec_exposure_dark', 'onesec_exposure_dark', 'oneandahalfsec_exposure_dark', 'twosec_exposure_dark', 'threepointfivesec_exposure_dark', 'fivesec_exposure_dark',  'sevenpointfivesec_exposure_dark', 'tensec_exposure_dark', 'fifteensec_exposure_dark', 'twentysec_exposure_dark', 'thirtysec_exposure_dark', 'broadband_ss_biasdark', 'narrowband_ss_biasdark']:
            a_dark_exposure = True
        else:
            a_dark_exposure = False

        if imtype.lower() in (
            "bias",
            "dark",
            "screenflat",
            "skyflat",
            "nearflat",
            "thorflat",
            "arcflat",
            "lampflat",
            "solarflat",
        ) or a_dark_exposure:
            skip_daytime_check = True
            skip_calibration_check = True

        if not skip_daytime_check and g_dev['obs'].daytime_exposure_time_safety_on:

            sun_az, sun_alt = self.obs.astro_events.sun_az_alt_now()

            if sun_alt > -5:
                if exposure_time > float(self.settings['max_daytime_exposure']):
                    g_dev['obs'].send_to_user("Exposure time reduced to maximum daytime exposure time: " + str(
                        float(self.settings['max_daytime_exposure'])))
                    plog("Exposure time reduced to maximum daytime exposure time: " + str(
                        float(self.settings['max_daytime_exposure'])))
                    exposure_time = float(
                        self.settings['max_daytime_exposure'])

        # Need to check that we are not in the middle of flats, biases or darks

        # Fifth thing, check that the sky flat latch isn't on
        # (I moved the scope during flats once, it wasn't optimal)
        if not skip_calibration_check:

            # or g_dev['seq'].sky_flat_latch:
            if g_dev['seq'].morn_sky_flat_latch or g_dev['seq'].eve_sky_flat_latch:

                g_dev['obs'].send_to_user(
                    "Refusing exposure request as the observatory is currently taking flats.")
                plog(
                    "Refusing exposure request as the observatory is currently taking flats.")
                self.running_an_exposure_set = False
                return

        if imtype.lower() in ("bias"):
            exposure_time = 0.0
            bias_dark_or_light_type_frame = 'bias'  # don't open the shutter.
            frame_type = imtype.replace(" ", "")

        elif imtype.lower() in ("dark", "lamp flat") or a_dark_exposure:

            bias_dark_or_light_type_frame = 'dark'  # don't open the shutter.
            lamps = "turn on led+tungsten lamps here, if lampflat"
            frame_type = imtype.replace(" ", "")

        elif imtype.lower() in ("nearflat", "thorflat", "arcflat"):
            bias_dark_or_light_type_frame = 'light'
            lamps = "turn on ThAr or NeAr lamps here"
            frame_type = "arc"
        elif imtype.lower() in ("skyflat", "screenflat", "solarflat"):
            bias_dark_or_light_type_frame = 'light'  # open the shutter.
            lamps = "screen lamp or none"
            frame_type = imtype.replace(
                " ", ""
            )  # note banzai doesn't appear to include screen or solar flat keywords.
        elif imtype.lower() == "focus" :
            frame_type = "focus"
            bias_dark_or_light_type_frame = 'light'
            smartstack = False
            lamps = None
        elif  imtype.lower() == "focus_confirmation":
            frame_type = "focus_confirmation"
            bias_dark_or_light_type_frame = 'light'
            smartstack = False
            lamps = None
        elif imtype.lower() == "pointing":
            frame_type = "pointing"
            bias_dark_or_light_type_frame = 'light'
            smartstack = False
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

        self.native_bin = self.settings["native_bin"]
        # self.ccd_sum = str(1) + ' ' + str(1)

        self.estimated_readtime = (
            exposure_time + self.readout_time
        )

        # Here we set up the filter, and later on possibly rotational composition.
        # default to using the main filter wheel, unless a specific one is specified
        fw_device = self.obs.devices['main_fw']
        if filterwheel_device is not None:
            fw_device = filterwheel_device

        try:
            null_filterwheel = fw_device.null_filterwheel
        except:
            null_filterwheel =True

        try:
            if not null_filterwheel:
                if imtype in ['bias', 'dark'] or a_dark_exposure:
                    requested_filter_name = 'dk'
                    # NB NB not here, but we could index the perseus to get the camera
                    # more out of the beam.
                elif imtype in ['pointing'] and self.settings['is_osc']:
                    requested_filter_name = 'lum'
                else:
                    # If the filter wheel is sent a filter name that it doesn't
                    # have, it will automatically use the default defined in the config
                    requested_filter_name = optional_params.get('filter')

                # Change the filter
                # Note: the filterwheel will know if it is already set correctly
                # so no need to check that here
                self.current_filter = fw_device.current_filter_name
                try:
                    self.current_filter, filter_number, filter_offset = fw_device.set_name_command(
                        {"filter": requested_filter_name}, {}
                    )
                    self.current_offset = filter_offset
                except:
                    plog("Failed to change filter! Cancelling exposure.")
                    plog(traceback.format_exc())
                    self.running_an_exposure_set = False
                    return 'filterwheel_error'

                # Handle unavailable filters
                # This is because the requested filter isn't available,
                # and we couldn't match with a reasonable substitute.
                if self.current_filter == "none" or self.current_filter == None:
                    plog("skipping exposure as no adequate filter match found")
                    g_dev["obs"].send_to_user(
                        "Skipping Exposure as no adequate filter found for requested observation")
                    self.running_an_exposure_set = False
                    return 'requested_filter_not_found'

                self.current_filter = fw_device.current_filter_name
                exposure_filter_offset = self.current_offset
            else:
                #plog('Warning: null filterwheel detected, skipping filter setup')
                exposure_filter_offset = 0
                requested_filter_name = 'none'
                self.current_filter = None
        except Exception as e:
            plog("Camera filter setup:  ", e)
            plog(traceback.format_exc())

        # plog ("REQUESTED FILTER NAME: " + str(requested_filter_name))
        # plog ("CURRENT FILTER: " + str(self.current_filter))
        this_exposure_filter = copy.deepcopy( self.current_filter)
        # plog ("THIS EXPOSURE FILTER: " + str(this_exposure_filter))

        # Always check rotator just before exposure  The Rot jitters when parked so
        # this gives rot_moving report during bias darks
        rot_report = 0
        if g_dev['rot'] != None:
            if not g_dev['mnt'].rapid_park_indicator and not g_dev['obs'].rotator_has_been_checked_since_last_slew:
                g_dev['obs'].rotator_has_been_checked_since_last_slew = True
                while g_dev['rot'].rotator.IsMoving:
                    if rot_report == 0 and (imtype not in ['bias', 'dark'] or a_dark_exposure):
                        plog("Waiting for camera rotator to catch up. ")
                        g_dev["obs"].send_to_user(
                            "Waiting for camera rotator to catch up before exposing.")

                        rot_report = 1
                    time.sleep(0.2)
                    if g_dev["obs"].stop_all_activity:
                        Nsmartstack = 1
                        sskcounter = 2
                        plog('stop_all_activity cancelling camera exposure')
                        self.running_an_exposure_set = False
                        return

        num_retries = 0
        incoming_exposure_time = copy.deepcopy(exposure_time)
        g_dev['obs'].request_scan_requests()
        if g_dev['seq'].blockend != None:
            g_dev['seq'].schedule_manager.update_now()

        unique_batch_code=self.obs.name + '_' + str(datetime.now()).replace(' ','_').replace('.','d').replace(':','-')
        for seq in range(count):

            # SEQ is the outer repeat loop and takes count images; those individual exposures are wrapped in a
            # retry-3-times framework with an additional timeout included in it.

            g_dev["obs"].request_update_status()


            now = ephem.Date(ephem.now())
            exposure_end_time = ephem.Date(ephem.now() + (exposure_time * ephem.second))
            observing_ends = self.obs.events['Observing Ends']
            naut_dusk = self.obs.events['Naut Dusk']
            naut_dawn = self.obs.events['Naut Dawn']
            observing_begins = self.obs.events['Observing Begins']


            if imtype.lower() in ["light", "expose"] and not self.obs.scope_in_manual_mode:
                # Exposure time must end before the end of the nighttime observing window
                if observing_ends < exposure_end_time:
                    plog("Sorry, exposures are outside of night time.")
                    self.running_an_exposure_set = False
                    return 'outsideofnighttime'
                # Reject exposures that start before nautical dusk or end after nautical dawn
                if now < observing_begins or exposure_end_time > observing_ends :
                    plog("Sorry, exposures are outside of night time.")
                    self.running_an_exposure_set = False
                    return 'outsideofnighttime'

            self.pre_mnt = []
            self.pre_rot = []
            self.pre_foc = []
            self.pre_ocn = []

            # Within each count - which is a single requested exposure, IF it is a smartstack
            # Then we divide each count up into individual smartstack exposures.
            ssBaseExp = self.settings['smart_stack_exposure_time']
            ssExp = self.settings['smart_stack_exposure_time']
            ssNBmult = self.settings['smart_stack_exposure_NB_multiplier']
            dark_exp_time = self.settings['dark_exposure']

            Nsmartstack = 1
            SmartStackID = 'no'
            smartstackinfo = 'no' # Just initialising this variable
            if not null_filterwheel:
                if this_exposure_filter.lower() in ['ha', 'o3', 's2', 'n2', 'y', 'up', 'u', 'su', 'sv', 'sb', 'z', 'hb', 'hbc', 'hd', 'hg', 'zp', 'zs']:
                    # For narrowband and low throughput filters, increase base exposure time.
                    ssExp = ssExp * ssNBmult
            else:
                try:
                    this_exposure_filter = fw_device.name
                except:
                    this_exposure_filter = 'RGGB'

            if not imtype.lower() in ["light", "expose"]:
                Nsmartstack = 1
                SmartStackID = 'no'
                smartstackinfo = 'no'
                exposure_time = incoming_exposure_time

            elif (smartstack == 'yes' or smartstack == True) and (incoming_exposure_time > ssExp):
                Nsmartstack = np.ceil(incoming_exposure_time / ssExp)
                exposure_time = ssExp
                SmartStackID = datetime.now().strftime("%d%m%y%H%M%S")
                if this_exposure_filter.lower() in ['ha', 'o3', 's2', 'n2', 'y', 'up', 'u', 'su', 'sv', 'sb', 'z', 'hb', 'hbc', 'hd', 'hg', 'zp', 'zs']:
                    smartstackinfo = 'narrowband'
                else:
                    smartstackinfo = 'broadband'

                # Here is where we quantise the exposure time for short exposures
                if incoming_exposure_time < 2:
                    exposure_snap_to_grid = [ 0.00004, 0.0004, 0.0045, 0.015, 0.05,0.1, 0.25, 0.5 , 0.75, 1, 1.5, 2.0]
                    exposure_time=min(exposure_snap_to_grid, key=lambda x:abs(x-incoming_exposure_time))
                else:
                    exposure_time = ssExp

            # Create a unique yet arbitrary code for the token
            token_timestamp = str(datetime.now()).replace(' ', '').replace('-', '').replace(':', '').replace('.', '')
            real_time_token = f"{g_dev['name']}_{self.alias}_{g_dev['day']}_{this_exposure_filter.lower()}_{smartstackinfo}_{ssBaseExp}_{ssBaseExp * ssNBmult}_{dark_exp_time}_{token_timestamp}"
            real_time_files = []

            self.retry_camera = 1
            self.retry_camera_start_time = time.time()

            if Nsmartstack > 1:
                self.currently_in_smartstack_loop = True
                self.initial_smartstack_ra = g_dev['mnt'].return_right_ascension(
                )
                self.initial_smartstack_dec = g_dev['mnt'].return_declination()
            else:
                self.initial_smartstack_ra = None
                self.initial_smartstack_dec = None
                self.currently_in_smartstack_loop = False


            # Repeat camera acquisition loop to collect all smartstacks necessary
            # The variable Nsmartstacks defaults to 1 - e.g. normal functioning
            # When a smartstack is not requested.
            for sskcounter in range(int(Nsmartstack)):
                pre_exposure_overhead_timer = time.time()
                # If the pier just flipped, trigger a recentering exposure.
                if not g_dev['obs'].mountless_operation:
                    if not g_dev['mnt'].rapid_park_indicator:
                        if g_dev['mnt'].pier_flip_detected==True and not g_dev['obs'].auto_centering_off:
                            plog ("PIERFLIP DETECTED, RECENTERING.")
                            g_dev["obs"].send_to_user("Pier Flip detected, recentering.")
                            g_dev['obs'].pointing_recentering_requested_by_platesolve_thread = True
                            g_dev['obs'].pointing_correction_request_time = time.time()
                            g_dev['obs'].pointing_correction_request_ra = g_dev["mnt"].last_ra_requested
                            g_dev['obs'].pointing_correction_request_dec = g_dev["mnt"].last_dec_requested
                            g_dev['obs'].pointing_correction_request_ra_err = 0
                            g_dev['obs'].pointing_correction_request_dec_err = 0
                            g_dev['obs'].check_platesolve_and_nudge(
                                no_confirmation=False)
                            Nsmartstack = 1
                            sskcounter = 2
                            self.currently_in_smartstack_loop = False
                            break
                        else:
                            pass

                    if g_dev['obs'].pointing_recentering_requested_by_platesolve_thread:
                        if not  g_dev['obs'].auto_centering_off:
                            g_dev['obs'].check_platesolve_and_nudge()
                            plog("Tel was just nudged after pier flip")

                self.tempStartupExposureTime = time.time()

                if Nsmartstack > 1:
                    plog("Smartstack " + str(sskcounter+1) +
                         " out of " + str(Nsmartstack))
                    g_dev["obs"].request_update_status()

                self.retry_camera = 1
                self.retry_camera_start_time = time.time()
                while self.retry_camera > 0:
                    if g_dev["obs"].stop_all_activity:
                        Nsmartstack=1
                        sskcounter=2
                        g_dev["obs"].stop_all_activity = False
                        plog("Camera retry loop stopped by Cancel Exposure")
                        self.running_an_exposure_set = False
                        self.currently_in_smartstack_loop=False
                        self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)
                        return 'stopcommand'

                    # Check that the block isn't ending during normal observing time (don't check while biasing, flats etc.)
                    # Only do this check if a block end was provided.
                    if g_dev['seq'].blockend != None:

                        # Check that the exposure doesn't go over the end of a block
                        endOfExposure = datetime.now(tz=timezone.utc) + timedelta(seconds=exposure_time)
                        now_date_timeZ = endOfExposure.isoformat().split('.')[0] + 'Z'
                        blockended = now_date_timeZ >= g_dev['seq'].blockend

                        if blockended or ephem.Date(ephem.now() + (exposure_time * ephem.second)) >= \
                                g_dev['events']['End Morn Bias Dark']:
                            plog(
                                "Exposure overlays the end of a block or the end of observing. Skipping Exposure.")
                            plog("And Cancelling SmartStacks.")
                            Nsmartstack = 1
                            sskcounter = 2
                            self.running_an_exposure_set = False
                            self.currently_in_smartstack_loop = False
                            self.write_out_realtimefiles_token_to_disk(
                                real_time_token, real_time_files)
                            return 'blockend'

                    # Stop if we're running from a block that has finished
                    if calendar_event_id is not None:
                        if not g_dev['seq'].schedule_manager.calendar_event_is_active(calendar_event_id):
                            plog('Calendar event is no longer active; cancelling current camera activity.')
                            Nsmartstack = 1
                            sskcounter = 2
                            self.currently_in_smartstack_loop = False
                            self.write_out_realtimefiles_token_to_disk(real_time_token, real_time_files)
                            self.running_an_exposure_set = False
                            return 'calendarend'


                    if not g_dev['obs'].assume_roof_open and not g_dev['obs'].scope_in_manual_mode and 'Closed' in g_dev['obs'].enc_status['shutter_status'] and imtype not in ['bias', 'dark'] and not a_dark_exposure:

                        plog("Roof shut, exposures cancelled.")
                        g_dev["obs"].send_to_user(
                            "Roof shut, exposures cancelled.")

                        self.open_and_enabled_to_observe = False
                        if not g_dev['seq'].morn_bias_dark_latch and not g_dev['seq'].bias_dark_latch:
                            # NB Kills bias dark
                            g_dev['obs'].cancel_all_activity()
                        if not g_dev['mnt'].rapid_park_indicator:
                            if g_dev['mnt'].home_before_park:
                                g_dev['mnt'].home_command()
                            g_dev['mnt'].park_command()
                        plog("And Cancelling SmartStacks.")
                        Nsmartstack = 1
                        sskcounter = 2
                        self.currently_in_smartstack_loop = False
                        self.write_out_realtimefiles_token_to_disk(
                            real_time_token, real_time_files)
                        self.running_an_exposure_set = False
                        return 'roofshut'

                    try:
                        if self.maxim or self.ascom or self.theskyx  or self.zwo or self.qhydirect or self.dummy:

                            ldr_handle_time = None
                            ldr_handle_high_time = None  # This is not maxim-specific

                            if self.has_darkslide and bias_dark_or_light_type_frame == 'light':
                                if self.darkslide_state != 'Open':
                                    if self.darkslide_type == 'COM':
                                        if not self.darkslide_instance.openDarkslide():
                                            self.currently_in_smartstack_loop = False
                                            self.write_out_realtimefiles_token_to_disk(
                                                real_time_token, real_time_files)
                                            self.running_an_exposure_set = False
                                            plog(
                                                "Darkslide Failed. Cancelling exposure")
                                            return 'darkslidefail'
                                    elif self.darkslide_type == 'ASCOM_FLI_SHUTTER':
                                        self.camera.Action(
                                            'SetShutter', 'open')
                                    self.darkslide_open = True
                                    self.darkslide_state = 'Open'
                            elif self.has_darkslide and (bias_dark_or_light_type_frame == 'bias' or bias_dark_or_light_type_frame == 'dark'):
                                if self.darkslide_state != 'Closed':
                                    if self.darkslide_type == 'COM':
                                        if not self.darkslide_instance.closeDarkslide():
                                            self.currently_in_smartstack_loop = False
                                            self.write_out_realtimefiles_token_to_disk(
                                                real_time_token, real_time_files)
                                            self.running_an_exposure_set = False
                                            plog(
                                                "Darkslide Failed. Cancelling exposure")
                                            return 'darkslidefail'
                                        # self.darkslide_instance.closeDarkslide()
                                    elif self.darkslide_type == 'ASCOM_FLI_SHUTTER':
                                        self.camera.Action(
                                            'SetShutter', 'close')

                                    self.darkslide_open = False
                                    self.darkslide_state = 'Closed'

                            # Good spot to check if we need to nudge the telescope
                            if not  g_dev['obs'].auto_centering_off:
                                g_dev['obs'].check_platesolve_and_nudge()
                            g_dev['obs'].time_of_last_exposure = time.time()

                            observer_user_name = user_name

                            try:
                                self.user_id = user_id
                                if self.user_id != self.last_user_id:
                                    self.last_user_id = self.user_id
                                observer_user_id = self.user_id
                            except:
                                observer_user_id = 'Tobor'
                                plog("Failed user_id")

                            self.current_exposure_time = exposure_time

                            # Always check rotator just before exposure
                            if not g_dev['obs'].mountless_operation:
                                rot_report = 0
                                if g_dev['rot'] != None:
                                    if not g_dev['mnt'].rapid_park_indicator and not g_dev['obs'].rotator_has_been_checked_since_last_slew:
                                        g_dev['obs'].rotator_has_been_checked_since_last_slew = True

                                        while g_dev['rot'].rotator.IsMoving:
                                            if rot_report == 0 :
                                                plog("Waiting for camera rotator to catch up. ")
                                                g_dev["obs"].send_to_user("Waiting for instrument rotator to catch up before exposing.")


                                                rot_report = 1
                                            time.sleep(0.2)
                                            if g_dev["obs"].stop_all_activity:
                                                Nsmartstack = 1
                                                sskcounter = 2
                                                plog(
                                                    "stop_all_activity cancelling out of camera exposure")
                                                self.currently_in_smartstack_loop = False
                                                self.write_out_realtimefiles_token_to_disk(
                                                    real_time_token, real_time_files)
                                                self.running_an_exposure_set = False
                                                return 'stopcommand'

                            if (bias_dark_or_light_type_frame in ["bias", "dark"] or 'flat' in frame_type or a_dark_exposure) and not manually_requested_calibration:

                                # Check that the temperature is ok before accepting
                                current_camera_temperature, cur_humidity, cur_pressure, cur_pwm = (
                                    self._temperature())
                                current_camera_temperature = float(
                                    current_camera_temperature)
                                if abs(float(current_camera_temperature) - float(self.setpoint)) > self.temp_tolerance:
                                    plog("temperature out of +/- range for calibrations (" + str(
                                        current_camera_temperature)+"), NOT attempting calibration frame")
                                    g_dev['obs'].camera_sufficiently_cooled_for_calibrations = False
                                    expresult = {}
                                    expresult["error"] = True
                                    expresult["patch"] = None
                                    self.running_an_exposure_set = False
                                    self.currently_in_smartstack_loop = False
                                    self.write_out_realtimefiles_token_to_disk(
                                        real_time_token, real_time_files)
                                    return expresult
                                else:
                                    g_dev['obs'].camera_sufficiently_cooled_for_calibrations = True



                            # Check there hasn't been a cancel sent through
                            if g_dev["obs"].stop_all_activity:
                                plog(
                                    "stop_all_activity cancelling out of camera exposure")
                                Nsmartstack = 1
                                sskcounter = 2
                                self.currently_in_smartstack_loop = False
                                self.write_out_realtimefiles_token_to_disk(
                                    real_time_token, real_time_files)
                                self.running_an_exposure_set = False
                                return 'cancelled'

                            if not g_dev['obs'].mountless_operation and not g_dev['mnt'].rapid_park_indicator \
                                and not  g_dev['obs'].mount_reference_model_off \
                                and not  g_dev['obs'].auto_centering_off:      #NB NB this last two may be and 'OR' ?? WER
                                # g_dev['mnt'].wait_for_slew(wait_after_slew=False)
                                if g_dev['mnt'].pier_flip_detected == True:
                                    plog(
                                        "Detected a pier flip just before exposure! Line 3608 in Camera.")
                                    g_dev["obs"].send_to_user(
                                        "Pier Flip detected, recentering.")
                                    g_dev['obs'].pointing_recentering_requested_by_platesolve_thread = True
                                    g_dev['obs'].pointing_correction_request_time = time.time(
                                    )
                                    g_dev['obs'].pointing_correction_request_ra = g_dev["mnt"].last_ra_requested
                                    g_dev['obs'].pointing_correction_request_dec = g_dev["mnt"].last_dec_requested
                                    g_dev['obs'].pointing_correction_request_ra_err = 0
                                    g_dev['obs'].pointing_correction_request_dec_err = 0
                                    g_dev['obs'].check_platesolve_and_nudge(
                                        no_confirmation=False)
                                    Nsmartstack = 1
                                    sskcounter = 2
                                    self.currently_in_smartstack_loop = False


                            if imtype in ['bias', 'dark'] or a_dark_exposure:
                                # Artifical wait time for bias and dark
                                # calibrations to allow pixels to cool
                                time.sleep(1)

                            if not imtype in ['bias', 'dark'] and not a_dark_exposure and not frame_type[-4:] == "flat" and not g_dev['obs'].scope_in_manual_mode:

                                if g_dev['events']['Morn Sky Flats'] < g_dev['events']['Sun Rise']:
                                    last_time = g_dev['events']['Morn Sky Flats']
                                else:
                                    last_time = g_dev['events']['Sun Rise']

                                if last_time < ephem.Date(ephem.now()):
                                    plog(
                                        "Observing has ended for the evening, cancelling out of exposures.")
                                    g_dev["obs"].send_to_user(
                                        "Observing has ended for the evening, cancelling out of exposures.")
                                    Nsmartstack = 1
                                    sskcounter = 2
                                    self.currently_in_smartstack_loop = False
                                    self.running_an_exposure_set = False
                                    return 'outsideofnighttime'
                                    #break

                            # Sort out if it is a substack
                            # If request actually requested a substack
                            if self.substacker:
                                self.substacker = False
                                broadband_ss_biasdark_exp_time = self.settings['smart_stack_exposure_time']
                                narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * \
                                    self.settings['smart_stack_exposure_NB_multiplier']
                                if self.settings['substack'] and not g_dev['seq'].focussing: # Don't substack while focussing
                                    if not imtype in ['bias', 'dark'] and not a_dark_exposure and not frame_type[-4:] == "flat" and not frame_type == 'pointing':
                                        if exposure_time % 10 == 0 and exposure_time >= 30 and exposure_time < 1.25 * narrowband_ss_biasdark_exp_time:
                                            self.substacker = True

                            # If it is meant to be a substacker image
                            # Make sure there is actually a bias, dark, flat and bpm
                            # otherwise a substack is pointless.
                            if self.substacker:
                                self.substacker = False
                                # Must have a biasdark
                                if 'tensec_exposure_biasdark' in self.darkFiles:
                                    if (this_exposure_filter.lower() + '_bin1' in self.flatFiles) or (this_exposure_filter + '_bin1' in self.flatFiles):
                                        if '1' in self.bpmFiles:
                                            self.substacker = True
                                        else:
                                            plog("Could not engage substacking as the bad pixel mask is missing")
                                    else:
                                        plog ("Could not engage substacking as the filter requested has no flat")
                                else:
                                    plog("Could not engage substacking as the appropriate biasdark")

                            # Adjust pointing exposure time relative to previously known focus
                            if not g_dev['seq'].focussing and not g_dev['obs'].scope_in_manual_mode and frame_type == 'pointing':
                                try:
                                    last_fwhm = g_dev['obs'].fwhmresult["FWHM"]
                                    #  NB NB WER this can be evil if telescope is not well set up. Should not adjust in Eng mode.

                                    if self.pixscale == None: #If we don't have a pixelscale  we don't really know what the seeing is, but best to give it a little increase
                                        exposure_time=exposure_time * 2
                                    elif last_fwhm > 7.0:
                                        exposure_time = exposure_time * 4
                                    elif last_fwhm > 4.5:
                                        exposure_time = exposure_time * 3
                                    elif last_fwhm > 2.5:
                                        exposure_time = exposure_time * 1.75
                                    elif last_fwhm > 2.0:
                                        exposure_time = exposure_time * 1.25
                                except:
                                    plog(
                                        "can't adjust exposure time for pointing if no previous focus known")

                            if not null_filterwheel:
                                while fw_device.filter_changing:
                                    time.sleep(0.05)

                            if not g_dev['obs'].scope_in_manual_mode:
                                g_dev['foc'].adjust_focus()

                            reporty = 0
                            while g_dev['foc'].focuser_is_moving:
                                if reporty == 0:
                                    reporty = 1
                                time.sleep(0.05)

                            # For some focusers, there is a non-trivial vibration time to
                            # wait until the mirror settles down before exposure
                            # that isn't even caught in the focuser threads.
                            # So if it has moved, as indicated by reporty
                            # Then there is a further check before moving on
                            if reporty == 1:
                                tempfocposition = g_dev['foc'].get_position_actual(
                                )
                                while True:
                                    time.sleep(0.2)
                                    nowfocposition = g_dev['foc'].get_position_actual(
                                    )
                                    if tempfocposition == nowfocposition:
                                        break
                                    else:
                                        plog("Detecting focuser still changing.")
                                        tempfocposition = copy.deepcopy(
                                            nowfocposition)

                            g_dev['mnt'].wait_for_slew()

                            # Initialise this variable here
                            self.substacker_filenames = []
                            self.start_time_of_observation = time.time()
                            self.shutter_open = True

                            # =============================================================================
                            # Start the exposure!
                            # =============================================================================
                            self._expose(exposure_time, bias_dark_or_light_type_frame)
                            self.end_of_last_exposure_time = time.time()


                            # After sending the exposure command, the camera is exposing
                            # So commands placed here are essentially "cost-free" in terms of overhead.
                            # As long as they don't take longer than the actual exposure time

                            # Make sure the latest mount_coordinates are updated. HYPER-IMPORTANT!
                            # But not so important if you aren't platesovling - e.g. short exposures
                            if not g_dev['obs'].mountless_operation:
                                if exposure_time >= 1:
                                    ra_at_time_of_exposure, dec_at_time_of_exposure = g_dev["mnt"].get_mount_coordinates_after_next_update()
                                else:
                                    ra_at_time_of_exposure = g_dev["mnt"].current_icrs_ra
                                    dec_at_time_of_exposure = g_dev["mnt"].current_icrs_dec
                            else:
                                ra_at_time_of_exposure = 99.9
                                dec_at_time_of_exposure = 99.9

                            if not g_dev['obs'].mountless_operation:
                                airmass = round(g_dev['mnt'].airmass, 4)

                                airmass_of_observation = airmass
                                g_dev["airmass"] = float(
                                    airmass_of_observation)

                                azimuth_of_observation = g_dev['mnt'].az
                                altitude_of_observation = g_dev['mnt'].alt
                            else:
                                airmass_of_observation = 99.9

                                azimuth_of_observation = 99.9
                                altitude_of_observation = 99.9

                            # The values above are where the mount thinks it is pointing.
                            # We also need where it IS pointing, which we can't know ahead of time
                            # exactly... although we do know we center on the requested RA and DEC
                            # pretty closely, so we can use that. Thats close enough for our
                            # uses in the site code. The pipeline replaces the RA and DEC
                            # with thorough platesolved versions later on.
                            if g_dev['obs'].mountless_operation:
                                corrected_ra_for_header=0.0
                                corrected_dec_for_header=0.0
                            else:
                                corrected_ra_for_header=g_dev["mnt"].last_ra_requested
                                corrected_dec_for_header=g_dev["mnt"].last_dec_requested

                        else:
                            plog("Something terribly wrong, driver not recognized.!")
                            expresult = {}
                            expresult["error"] = True
                            self.running_an_exposure_set = False
                            self.shutter_open = False
                            self.currently_in_smartstack_loop = False
                            self.write_out_realtimefiles_token_to_disk(real_time_token, real_time_files)
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
                            plog("couldn't grab quick status focus")

                        if not g_dev['obs'].mountless_operation:
                            g_dev["mnt"].get_rapid_exposure_status(
                                self.pre_mnt
                            )

                        expresult = self.finish_exposure(
                            exposure_time,
                            frame_type,
                            count - seq,
                            optional_params=optional_params,
                            solve_it=solve_it,
                            smartstackid=SmartStackID,
                            # longstackid=LongStackID,
                            sskcounter=sskcounter,
                            Nsmartstack=Nsmartstack,
                            exposure_filter_offset=exposure_filter_offset,
                            ra_at_time_of_exposure=ra_at_time_of_exposure,
                            dec_at_time_of_exposure=dec_at_time_of_exposure,
                            observer_user_name=observer_user_name,
                            observer_user_id=observer_user_id,
                            airmass_of_observation=airmass_of_observation,
                            azimuth_of_observation=azimuth_of_observation,
                            altitude_of_observation=altitude_of_observation,
                            manually_requested_calibration=manually_requested_calibration,
                            zoom_factor=zoom_factor,
                            useastrometrynet=useastrometrynet,
                            a_dark_exposure=a_dark_exposure,
                            substack=self.substacker,
                            corrected_ra_for_header=corrected_ra_for_header,
                            corrected_dec_for_header=corrected_dec_for_header,
                            fw_device=fw_device,
                            null_filterwheel=null_filterwheel,
                            unique_batch_code=unique_batch_code,
                            count=count,
                            upload_metadata=upload_metadata
                        )
                        #breakpoint()   WERexplore
                        self.retry_camera = 0
                        if not frame_type[-4:] == "flat" and not frame_type.lower() in ["bias", "dark"] and not a_dark_exposure and not frame_type.lower() == 'focus' and not frame_type == 'pointing':
                            try:
                                real_time_files.append(
                                    str(expresult["real_time_filename"]))
                            except:
                                print(
                                    "Did not include real time filename due to exposure cancelling (probably)")
                        break
                    except Exception as e:
                        plog("Exception in camera retry loop:  ", e)
                        plog(traceback.format_exc())
                        self.retry_camera -= 1
                        num_retries += 1
                        self.shutter_open = False
                        continue
            self.currently_in_smartstack_loop = False


            self.write_out_realtimefiles_token_to_disk(real_time_token,real_time_files)

        # If the pier just flipped, trigger a recentering exposure.
        # This is here because a single exposure may have a flip in it, hence
        # we check here.
        if not g_dev['obs'].mountless_operation:
            if not g_dev['mnt'].rapid_park_indicator:
                if g_dev['mnt'].pier_flip_detected == True  and not g_dev['obs'].auto_centering_off:
                    plog ("!!!!!!!!!!!PIERFLIP DETECTED, RECENTERING!!!!!!!!!!!!!!!!!")
                    g_dev["obs"].send_to_user("Pier Flip detected, recentering.")
                    g_dev['obs'].pointing_recentering_requested_by_platesolve_thread = True
                    g_dev['obs'].pointing_correction_request_time = time.time()
                    g_dev['obs'].pointing_correction_request_ra = g_dev["mnt"].last_ra_requested
                    g_dev['obs'].pointing_correction_request_dec = g_dev["mnt"].last_dec_requested
                    g_dev['obs'].pointing_correction_request_ra_err = 0
                    g_dev['obs'].pointing_correction_request_dec_err = 0
                    g_dev['obs'].check_platesolve_and_nudge(
                        no_confirmation=False)
                else:
                    pass

        #self.write_out_realtimefiles_token_to_disk(real_time_token, real_time_files)

        #  This is the loop point for the seq count loop
        self.currently_in_smartstack_loop = False
        # trap missing expresult (e.g. cancelled exposures etc.)
        if not 'expresult' in locals():
            expresult = 'error'
        self.running_an_exposure_set = False
        self.shutter_open = False
        return expresult

    def write_out_realtimefiles_token_to_disk(self, token_name, real_time_files):
        """
        Write out real-time files token to disk for tracking.

        Args:
            token_name (str): Token for real-time file tracking
            real_time_files (list): List of real-time file paths
        """

        # Append the seq number to the token_name
        # As it is possible to have two images taken very close in time
        token_name=token_name + str(self.next_seq)


        if self.site_config['save_raws_to_pipe_folder_for_nightly_processing']:
            if len(real_time_files) > 0:

                # This is the failsafe directory.... if it can't be written to the PIPE folder
                # Which is usually a shared drive on the network, it gets saved here
                failsafe_directory=self.site_config['archive_path'] + 'failsafe'
                if not os.path.exists(failsafe_directory):
                    os.umask(0)
                    os.makedirs(failsafe_directory)
                failsafetokenfolder=failsafe_directory+ '/tokens'
                if not os.path.exists(failsafe_directory+ '/tokens'):
                    os.umask(0)
                    os.makedirs(failsafe_directory+ '/tokens')

                try:
                    pipetokenfolder = self.site_config['pipe_archive_folder_path'] + '/tokens'
                    if not os.path.exists(self.site_config['pipe_archive_folder_path'] + '/tokens'):
                        os.umask(0)
                        os.makedirs(self.site_config['pipe_archive_folder_path'] + '/tokens', mode=0o777)

                    if self.is_osc:
                        suffixes = ['B1', 'R1', 'G1', 'G2', 'CV']

                        temp_file_holder=[]
                        for suffix in suffixes:
                            for tempfilename in real_time_files:
                                temp_file_holder.append(tempfilename.replace('-EX00.', f'{suffix}-EX00.'))
                            try:
                                with open(f"{pipetokenfolder}/{token_name}{suffix}", 'w') as f:
                                    json.dump(temp_file_holder, f, indent=2)
                            except:
                                plog(traceback.format_exc())
                    else:
                        try:
                            with open(pipetokenfolder + "/" + token_name, 'w') as f:
                                json.dump(real_time_files, f, indent=2)
                        except:
                            plog(traceback.format_exc())
                except:
                    plog ("failed token upload to pipe folder, saving to failsafe")
                    # pipetokenfolder = self.site_config['pipe_archive_folder_path'] + '/tokens'
                    # if not os.path.exists(self.site_config['pipe_archive_folder_path'] + '/tokens'):
                    #     os.umask(0)
                    #     os.makedirs(self.site_config['pipe_archive_folder_path'] + '/tokens', mode=0o777)

                    if self.is_osc:
                        suffixes = ['B1', 'R1', 'G1', 'G2', 'CV']

                        temp_file_holder=[]
                        for suffix in suffixes:
                            for tempfilename in real_time_files:
                                temp_file_holder.append(tempfilename.replace('-EX00.', f'{suffix}-EX00.'))
                            try:
                                with open(f"{failsafetokenfolder}/{token_name}{suffix}", 'w') as f:
                                    json.dump(temp_file_holder, f, indent=2)
                            except:
                                plog(traceback.format_exc())
                    else:
                        try:
                            with open(failsafetokenfolder + "/" + token_name, 'w') as f:
                                json.dump(real_time_files, f, indent=2)
                        except:
                            plog(traceback.format_exc())


        if self.site_config['push_file_list_to_pipe_queue']:
            if len(real_time_files) > 0:

                #self.camera_path + g_dev["day"] + "/to_AWS/"

                token_name_s3='pipes3_'+token_name

                localtokenfolder = self.camera_path + g_dev["day"] + '/tokens'
                if not os.path.exists(localtokenfolder):
                    os.umask(0)
                    os.makedirs(localtokenfolder, mode=0o777)
                if self.is_osc:
                    suffixes = ['B1', 'R1', 'G1', 'G2', 'CV']

                    for suffix in suffixes:

                        temp_file_holder=[]
                        for tempfilename in real_time_files:
                            temp_file_holder.append(tempfilename.replace('-EX00.', f'{suffix}-EX00.'))
                        try:
                            with open(f"{localtokenfolder}/{token_name_s3}{suffix}", 'w') as f:
                                json.dump(temp_file_holder, f, indent=2)
                        except:
                            plog(traceback.format_exc())

                        #plonk it in the upload queue
                        try:
                            g_dev['obs'].enqueue_for_fastAWS( localtokenfolder+'/', token_name_s3 + suffix, 0)
                        except:
                            plog(traceback.format_exc())
                else: # not osc
                    try:
                        with open(localtokenfolder + "/" + token_name_s3, 'w') as f:
                            json.dump(real_time_files, f, indent=2)
                    except:
                        plog(traceback.format_exc())

                    #plonk it in the upload queue
                    try:
                        g_dev['obs'].enqueue_for_fastAWS( localtokenfolder+'/', token_name_s3, 0)
                    except:
                        plog(traceback.format_exc())


    def stop_command(self, required_params, optional_params):
        """Stop the current exposure and return the camera to Idle state."""
        self._stop_expose()
        self.expresult = {}
        self.expresult["stopped"] = True
        self.running_an_exposure_set = False
        self.shutter_open = False
        self.exposure_halted = True

    def finish_exposure(
        self,
        exposure_time,
        frame_type,
        counter,
        optional_params=None,
        solve_it=False,
        smartstackid='no',
        sskcounter=0,
        Nsmartstack=1,
        exposure_filter_offset=None,
        ra_at_time_of_exposure=None,
        dec_at_time_of_exposure=None,
        observer_user_name=None,
        observer_user_id=None,
        airmass_of_observation=None,
        azimuth_of_observation=None,
        altitude_of_observation=None,
        manually_requested_calibration=False,
        zoom_factor=False,
        useastrometrynet=False,
        a_dark_exposure=False,
        substack=False,
        corrected_ra_for_header=0.0,
        corrected_dec_for_header=0.0,
        fw_device=None,
        null_filterwheel=True,
        unique_batch_code='blah',
        count=1,
        upload_metadata={}
    ):
        plog(f"Exposure Started: {exposure_time}s {frame_type}")

        # Set the observation dates
        # Format for DATE-OBS needs to be YYYY-MM-DDTHH:mm:ss.sss
        if not 'image_metadata' in upload_metadata:
            upload_metadata['image_metadata'] = {}
        if substack:
            upload_metadata['image_metadata']['DATE-OBS'] = datetime.fromtimestamp(self.substack_start_time, tz=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', '')
            upload_metadata['image_metadata']['DAY-OBS']  = datetime.fromtimestamp(self.substack_start_time, tz=timezone.utc).strftime("%Y%m%d")
        else:
            upload_metadata['image_metadata']['DATE-OBS'] = datetime.fromtimestamp(self.start_time_of_observation, tz=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', '')
            upload_metadata['image_metadata']['DAY-OBS']  = datetime.fromtimestamp(self.start_time_of_observation, tz=timezone.utc).strftime("%Y%m%d")

        # Simulate timing of exposure for dummy camera
        if self.dummy:
            time.sleep(exposure_time)

        obs_id = self.site_config['obs_id']

        if fw_device == None:
            fw_device = self.obs.devices['main_fw']

        try:
            this_exposure_filter = fw_device.current_filter_name
        except:
            this_exposure_filter = 'RGGB'

        if 'object_name' not in optional_params or optional_params['object_name'] == '':
            optional_params['object_name'] = 'Unknown'

        count = int(optional_params['count'])

        #NB NB we should create a code-wide list of Narrow bands, broadbands and widebands so we do not have mulitiple lists to manage.
        narrowband_filters = ['ha', 'hac', 'o3', 's2', 'n2', 'hb', 'hbc', 'hd', 'hga', 'cr', 'su', 'sv', 'sb', 'sy', 'hd', 'hg']
        # Send image info to the UI (observatory logs section)
        if frame_type in ("dark", "bias") or a_dark_exposure:
            g_dev["obs"].send_to_user(f"Starting {exposure_time}s calibration exposure.", p_level="INFO")
        elif frame_type in ("flat", "screenflat", "skyflat"):
            g_dev["obs"].send_to_user(f"Taking {exposure_time}s flat exposure.", p_level="INFO")
        elif frame_type in ("focus", "auto_focus", "pointing", "focus_confirmation"):
            g_dev["obs"].send_to_user(f"Starting {exposure_time}s {frame_type} exposure.", p_level="INFO")
        elif Nsmartstack > 1 and this_exposure_filter.lower() in narrowband_filters:
            message = (
                f"Starting narrowband {exposure_time}s "
                f"smartstack {sskcounter + 1} out of {int(Nsmartstack)} "
                f"of {optional_params['object_name']} by user: {observer_user_name}"
            )
            plog(message)
            g_dev["obs"].send_to_user(message, p_level="INFO")
        elif Nsmartstack > 1:
            message = (
                f"Starting broadband {exposure_time}s "
                f"smartstack {sskcounter + 1} out of {int(Nsmartstack)} "
                f"of {optional_params['object_name']} by user: {observer_user_name}"
            )
            plog(message)
            g_dev["obs"].send_to_user(message, p_level="INFO")
        else:
            message = (
                f"Starting {exposure_time}s {this_exposure_filter or 'filterless'} exposure "
                f"of {optional_params['object_name']} by user: {observer_user_name}. "
                f"{count - int(counter) + 1} of {count}"
            )
            g_dev["obs"].send_to_user(message, p_level="INFO")

        self.status_time = time.time() + 10
        self.post_mnt = []
        self.post_rot = []
        self.post_foc = []
        self.post_ocn = []
        counter = 0

        if substack:
            # It takes time to do the median stack... add in a bit of an empirical overhead
            # We also have to factor in all the readout times unlike a single exposure
            # As the readouts are all done in the substack thread.
            #stacking_overhead= 0.0005*pow(exposure_time,2) + 0.0334*exposure_time
            # , 'y', 'up', 'u']
            if this_exposure_filter.lower() in narrowband_filters:
                cycle_time = exposure_time + \
                    ((exposure_time / 30)) * \
                    self.readout_time  # + stacking_overhead
            else:
                cycle_time = exposure_time + \
                    ((exposure_time / 10)) * \
                    self.readout_time  # + stacking_overhead

            self.completion_time = self.start_time_of_observation + cycle_time

        # For file-based readouts, we need to factor in the readout time
        # and wait for that as well as the exposure time.
        # Currently this is just theskyx... probably also ascom and maxim but we don't use either of them anymore
        elif self.theskyx:
            # We have a 25% buffer so that it can record faster readout times.
            cycle_time = (0.75*self.readout_time)+exposure_time
            self.completion_time = self.start_time_of_observation + cycle_time
        # Otherwise just wait for the exposure_time to end
        # Because the readout time occurs in the image aquisition function
        else:
            cycle_time = exposure_time
            self.completion_time = self.start_time_of_observation + cycle_time

        expresult = {"error": False}
        quartileExposureReport = 0
        self.plog_exposure_time_counter_timer = time.time() - 3.0

        exposure_scan_request_timer = time.time() - 8
        g_dev["obs"].exposure_halted_indicator = False

        # This command takes 0.1s to do, so happens just during the start of exposures
        self.tempccdtemp, self.ccd_humidity, self.ccd_pressure, cur_pwm = (
            self._temperature())

        block_and_focus_check_done = False

        if exposure_time <= 5.0:
            g_dev['obs'].request_scan_requests()
            if g_dev['seq'].blockend != None:
                g_dev['seq'].schedule_manager.update_now()
            try:
                focus_position = g_dev['foc'].current_focus_position
            except:
                pass
            block_and_focus_check_done = True

        check_nudge_after_shutter_closed=False

        if frame_type[-5:] in ["focus", "probe", "ental"] or frame_type == "focus_confirmation":
            focus_image = True
        else:
            focus_image = False

        broadband_ss_biasdark_exp_time = self.settings['smart_stack_exposure_time']
        narrowband_ss_biasdark_exp_time = broadband_ss_biasdark_exp_time * \
            self.settings['smart_stack_exposure_NB_multiplier']
        # dark_exp_time = self.settings['dark_exposure']
        if not g_dev['obs'].mountless_operation:
            avg_mnt = g_dev["mnt"].get_average_status(self.pre_mnt, self.pre_mnt)
        else:
            avg_mnt = None

        try:
            avg_foc = g_dev["foc"].get_average_status(self.pre_foc, self.pre_foc)
        except:
            pass

        try:
            avg_rot = g_dev["rot"].get_average_status(
                self.pre_rot, self.pre_rot
            )
        except:
            avg_rot = None

        object_name = 'Unknown'
        object_specf = 'no'

        if "object_name" in optional_params:
            if (
                optional_params["object_name"] != "Unspecified"
                and optional_params["object_name"] != ""
            ):
                object_name = optional_params["object_name"]
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

        focus_position = g_dev['foc'].current_focus_position

        try:
            next_seq = next_sequence(self.alias)
        except:
            next_seq = reset_sequence(self.alias)

        self.next_seq = next_seq

        # RAW NAMES FOR FOCUS AND POINTING SETUP HERE
        im_path_r = self.camera_path
        im_path = im_path_r + g_dev["day"] + "/to_AWS/"
        im_type = "EX"
        f_ext = "-"
        try:
            cal_name   = f"{obs_id}-{self.alias}-{g_dev['day']}-{next_seq}{f_ext}-{im_type}00.fits"
            jpeg_name  = f"{obs_id}-{self.alias}-{g_dev['day']}-{next_seq}-{im_type}10.jpg"
            raw_name00 = f"{obs_id}-{self.alias}_{frame_type}_{this_exposure_filter}-{g_dev['day']}-{next_seq}-{im_type}00.fits"
            text_name  = f"{obs_id}-{self.alias}-{g_dev['day']}-{next_seq}-{im_type}00.txt"
            cal_path = im_path_r + g_dev["day"] + "/calib/"
            raw_path = im_path_r + g_dev['day'] + "/raw/"
            raw_basename = raw_name00.split('.')[0]
        except:
            plog(traceback.format_exc())

        if not os.path.exists(im_path_r):
            os.makedirs(im_path_r, mode=0o777)
        if not os.path.exists(im_path_r + g_dev["day"]):
            os.makedirs(im_path_r + g_dev["day"], mode=0o777)
        if not os.path.exists(im_path_r + g_dev["day"] + "/calib"):
            os.makedirs(im_path_r + g_dev["day"] + "/calib", mode=0o777)
        if not os.path.exists(im_path_r + g_dev["day"] + "/to_AWS"):
            os.makedirs(im_path_r + g_dev["day"] + "/to_AWS", mode=0o777)

        if self.site_config["save_to_alt_path"] == "yes":
            self.alt_path = self.site_config["alt_path"] + '/' + obs_id + '/'  # NB NB this should come from config file, it is site dependent.
            os.makedirs(self.alt_path, exist_ok=True, mode=0o777)
            os.makedirs(self.alt_path + g_dev["day"], exist_ok=True, mode=0o777)
            os.makedirs(self.alt_path + g_dev["day"] + "/raw/", exist_ok=True, mode=0o777)


        # FOR POINTING AND FOCUS EXPOSURES, CONSTRUCT THE SCALED MASTERDARK WHILE
        # THE EXPOSURE IS RUNNING
        if (frame_type=='pointing' or focus_image == True) and smartstackid == 'no':
            if not substack:
                try:
                    # Sort out an intermediate dark
                    fraction_through_range = 0
                    if exposure_time < 0.5:
                        intermediate_tempdark = (
                            self.darkFiles['halfsec_exposure_dark'])
                    elif exposure_time < 2.0:
                        fraction_through_range = (exposure_time-0.5)/(2.0-0.5)
                        intermediate_tempdark = (fraction_through_range * self.darkFiles['twosec_exposure_dark']) + (
                            (1-fraction_through_range) * self.darkFiles['halfsec_exposure_dark'])

                    elif exposure_time < 10.0:
                        fraction_through_range = (exposure_time-2)/(10.0-2.0)
                        intermediate_tempdark = (fraction_through_range * self.darkFiles['tensec_exposure_dark']) + (
                            (1-fraction_through_range) * self.darkFiles['twosec_exposure_dark'])

                    elif exposure_time < 30:
                        fraction_through_range = (
                            exposure_time-10)/(30.0-10.0)
                        intermediate_tempdark = (fraction_through_range * self.darkFiles["thirtysec_exposure_dark"]) + (
                            (1-fraction_through_range) * self.darkFiles['tensec_exposure_dark'])
                    else:
                        intermediate_tempdark = (
                            self.darkFiles["thirtysec_exposure_dark"])
                except:
                    try:
                        plog ("failed on making intermediate tempdark properly")
                        intermediate_tempdark = (self.darkFiles['1'])
                    except:
                        plog ("failed entirely on intermediate tempdark")
                        pass

            try:
                intermediate_tempflat = np.load(
                    self.flatFiles[this_exposure_filter + "_bin" + str(1)])
            except:
                plog("couldn't find flat for this filter")
                intermediate_tempflat = None
        ## For traditional exposures, spin up all the subprocesses ready to collect and process the files once they arrive
        if (not frame_type[-4:] == "flat" and
            not frame_type in ["bias", "dark"] and
            not frame_type == 'pointing' and
            not a_dark_exposure and
            not focus_image):

            ######### Trigger off threads to wait for their respective files

            ## Spin up tha main post_processing_thread
            post_processing_subprocess = subprocess.Popen(
                ['python','subprocesses/post_exposure_subprocess.py'],
                stdin=subprocess.PIPE,
                stdout=None,
                stderr=None,
                bufsize=-1
            )

            # SMARTSTACK THREAD
            if (not frame_type.lower() in [
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
            ] and
                smartstackid != 'no' and not a_dark_exposure):

                smartstackthread_filename = self.local_calibration_path + \
                    "smartstacks/smartstack" + \
                    str(time.time()).replace('.', '') + '.pickle'

                def clean_object_name(name):
                    """Convert object name to filename-safe format."""
                    return str(name).replace(':', 'd').replace('@', 'at').replace('.', 'd').replace(' ', '').replace('-', '')

                if self.site_config['save_reduced_file_numberid_first']:
                    clean_name = clean_object_name(object_name)
                    clean_exposure_time = str(exposure_time).replace('.', 'd')
                    red_name01 = f"{next_seq}-{obs_id}-{clean_name}-{this_exposure_filter}-{clean_exposure_time}-{im_type}01.fits"
                else:
                    clean_name = clean_object_name(object_name)
                    clean_exposure_time = str(exposure_time).replace('.', 'd')
                    red_name01 = f"{obs_id}-{clean_name}-{str(this_exposure_filter)}-{next_seq}-{clean_exposure_time}-{im_type}01.fits"


                try:
                    smartstack_subprocess = subprocess.Popen(
                        ['python', 'subprocesses/SmartStackprocess.py'],
                        stdin=subprocess.PIPE,
                        stdout=None,
                        bufsize=-1
                    )
                except:
                    plog.err('Smartstack subprocess failed to start')

                try:
                    smartstack_subprocess_inputs = {
                        "file_info": {
                            "smartstackthread_filename": smartstackthread_filename,
                            "smartstackid": smartstackid,
                            "obsid_path": self.local_calibration_path if self.settings["is_osc"] else self.obsid_path,
                            "jpeg_path": self.camera_path + g_dev['day'] + "/to_AWS/",
                            "jpeg_name": jpeg_name,
                            "red_path": im_path_r + g_dev['day'] + "/reduced/",
                            "red_name01": red_name01
                        },
                        "image_transforms": {
                            "transpose_jpeg": self.settings["transpose_jpeg"],
                            "flipx_jpeg": self.settings['flipx_jpeg'],
                            "flipy_jpeg": self.settings['flipy_jpeg'],
                            "rotate180_jpeg": self.settings['rotate180_jpeg'],
                            "rotate90_jpeg": self.settings['rotate90_jpeg'],
                            "rotate270_jpeg": self.settings['rotate270_jpeg'],
                            "pier_side": g_dev["mnt"].pier_side,
                            "squash_on_x_axis": self.settings["squash_on_x_axis"],
                            "zoom_factor": zoom_factor
                        },
                        "osc_settings": {
                            "is_osc": self.settings["is_osc"],
                            "osc_bayer": self.settings["osc_bayer"] if self.settings["is_osc"] else None,
                            "osc_brightness_enhance": self.settings['osc_brightness_enhance'] if self.settings["is_osc"] else 0,
                            "osc_contrast_enhance": self.settings['osc_contrast_enhance'] if self.settings["is_osc"] else 0,
                            "osc_colour_enhance": self.settings['osc_colour_enhance'] if self.settings["is_osc"] else 0,
                            "osc_saturation_enhance": self.settings['osc_saturation_enhance'] if self.settings["is_osc"] else 0,
                            "osc_sharpness_enhance": self.settings['osc_sharpness_enhance'] if self.settings["is_osc"] else 0
                        }
                    }

                    # Manual debugging flag
                    debug_smartstack = False
                    if debug_smartstack:
                        pickle.dump(smartstack_subprocess_inputs, open('subprocesses/testsmartstackpickle', 'wb'))
                    else:
                        pickle.dump(smartstack_subprocess_inputs, smartstack_subprocess.stdin)
                except:
                    plog.warn("Problem in the smartstack pickle dump")
                    plog.warn(traceback.format_exc())

                path_to_image_directory = f"{self.camera_path}{g_dev['day']}/to_AWS/"

                # Send the smartstack file to the upload queue
                self.obs.enqueue_for_fastAWS(path_to_image_directory, jpeg_name, exposure_time)

                # Upload smartstacked jpg to LCO archive
                if upload_metadata.get('is_lco_observation', False):
                    filepath = path_to_image_directory + jpeg_name
                    upload_metadata['image_metadata']['size'] = 'large'
                    upload_metadata['image_metadata']['frame_basename'] = raw_basename
                    self.obs.enqueue_for_lco_archive(
                        filepath,
                        metadata=upload_metadata['image_metadata'],
                        is_thumbnail=True,
                    )

            else:
                smartstackthread_filename='no'


            # Photometry Thread
            photometry_thread_filename = f"{self.local_calibration_path}smartstacks/sep{str(time.time()).replace('.', '')}.pickle"

            is_osc = self.settings["is_osc"]
            saturate = self.settings["saturate"]
            minimum_realistic_seeing=self.site_config['minimum_realistic_seeing']

            try:
                photometry_subprocess = subprocess.Popen(
                    ['python', 'subprocesses/photometry_process.py'],
                    stdin=subprocess.PIPE,
                    stdout=None,
                    bufsize=-1
                )
            except:
                plog.err('Photometry subprocess failed to start')

            try:
                photometry_subprocess_inputs = {
                    "file_info": {
                        "photometry_thread_filename": photometry_thread_filename,
                        "im_path": im_path,
                        "text_name": text_name,
                        "cal_path": cal_path,
                        "cal_name": cal_name
                    },
                    "camera_settings": {
                        "pixscale": self.pixscale,
                        "readnoise": self.camera_known_readnoise,
                        "native_bin": self.native_bin,
                        "saturate": saturate
                    },
                    "processing_options": {
                        "is_osc": is_osc,
                        "frame_type": frame_type,
                        "minimum_realistic_seeing": minimum_realistic_seeing
                    },
                    "metadata": {
                        "hduheader": 'hduheader',
                        "events": g_dev['events'],
                        "ephem_now": ephem.now(),
                        "exposure_time": exposure_time
                    }
                }

                # Here is a manual debug area which makes a pickle for debug purposes.
                # Default is False, but can be manually set to True for code debugging
                phot_debug = False
                if phot_debug:
                    pickle.dump(photometry_subprocess_inputs, open('subprocesses/test_photometry_subprocess_pickle', 'wb'))
                else:
                    pickle.dump(photometry_subprocess_inputs, photometry_subprocess.stdin)
            except:
                plog.warn("Problem in the photometry pickle dump")
                plog.warn(traceback.format_exc())

            packet = (avg_foc,exposure_time,this_exposure_filter, airmass_of_observation)
            self.obs.file_wait_and_act_queue.put((im_path + text_name.replace('.txt', '.fwhm'), time.time(), packet))

            # Send the fits header txt file to the s3 upload queue
            self.obs.enqueue_for_fastAWS(im_path, text_name, exposure_time)

            # JPEG process
            # Smartstack jpegs are done elsewhere and pointing jpegs are made by the platesolve routine
            if smartstackid == 'no' and not frame_type=='pointing':
                mainjpegthread_filename=self.local_calibration_path + "smartstacks/mainjpeg" + str(time.time()).replace('.','') + '.pickle'
                is_osc = self.settings["is_osc"]
                osc_bayer = self.settings["osc_bayer"]
                if is_osc:
                    osc_background_cut = self.settings['osc_background_cut']
                    osc_brightness_enhance = self.settings['osc_brightness_enhance']
                    osc_contrast_enhance = self.settings['osc_contrast_enhance']
                    osc_colour_enhance = self.settings['osc_colour_enhance']
                    osc_saturation_enhance = self.settings['osc_saturation_enhance']
                    osc_sharpness_enhance = self.settings['osc_sharpness_enhance']
                else:
                    osc_background_cut=0
                    osc_brightness_enhance= 0
                    osc_contrast_enhance=0
                    osc_colour_enhance=0
                    osc_saturation_enhance=0
                    osc_sharpness_enhance=0

                # These steps flip and rotate the jpeg according to the settings in the site-config for this camera
                transpose_jpeg = self.settings["transpose_jpeg"]
                flipx_jpeg = self.settings['flipx_jpeg']
                flipy_jpeg = self.settings['flipy_jpeg']
                rotate180_jpeg = self.settings['rotate180_jpeg']
                rotate90_jpeg = self.settings['rotate90_jpeg']
                rotate270_jpeg = self.settings['rotate270_jpeg']
                squash_on_x_axis = self.settings["squash_on_x_axis"]
                if g_dev['obs'].mountless_operation:
                    pier_side=0
                else:
                    pier_side=g_dev["mnt"].pier_side

                try:
                    jpeg_subprocess = subprocess.Popen(
                        ['python', 'subprocesses/mainjpeg.py'],
                        stdin=subprocess.PIPE,
                        stdout=None,
                        bufsize=-1
                    )
                except:
                    plog.err('JPEG subprocess failed to start')
                    plog.err(traceback.format_exc())

                jpeg_output_dir = self.camera_path + g_dev['day'] + "/to_AWS/"
                try:
                    mainjpeg_subprocess_inputs = {
                        "mainjpegthread_filename": mainjpegthread_filename,
                        "output_dir": jpeg_output_dir,
                        "jpeg_filename": jpeg_name,
                        "osc_settings": {
                            "is_osc": is_osc,
                            "bayer": osc_bayer,
                            "background_cut": osc_background_cut,
                            "brightness_enhance": osc_brightness_enhance,
                            "contrast_enhance": osc_contrast_enhance,
                            "colour_enhance": osc_colour_enhance,
                            "saturation_enhance": osc_saturation_enhance,
                            "sharpness_enhance": osc_sharpness_enhance
                        },
                        "jpeg_transforms": {
                            "pier_side": pier_side,
                            "transpose": transpose_jpeg,
                            "flipx": flipx_jpeg,
                            "flipy": flipy_jpeg,
                            "rotate180": rotate180_jpeg,
                            "rotate90": rotate90_jpeg,
                            "rotate270": rotate270_jpeg,
                            "squash_on_x_axis": squash_on_x_axis,
                            "zoom_factor": zoom_factor
                        }
                    }

                    # Here is a manual debug area which makes a pickle for debug purposes.
                    # Default is False, but can be manually set to True for code debugging
                    jpeg_debug = False
                    if jpeg_debug:
                        #NB set this path to create test pickle for makejpeg routine.
                        pickle.dump(mainjpeg_subprocess_inputs, open('testjpegpickle', 'wb'))
                    else:
                        pickle.dump(mainjpeg_subprocess_inputs, jpeg_subprocess.stdin)
                except:
                    plog.warn("Problem in the jpeg pickle dump")
                    plog.warn(traceback.format_exc())

                del jpeg_subprocess

                # Send the jpeg file to the upload queue
                # Note: this is for jpgs that aren't smartstacked.
                self.obs.enqueue_for_fastAWS( jpeg_output_dir, jpeg_name, exposure_time)

                # Upload non-smartstacked jpg to LCO archive
                if upload_metadata.get('is_lco_observation', False):
                    filepath = jpeg_output_dir + jpeg_name
                    upload_metadata['image_metadata']['size'] = 'large'
                    upload_metadata['image_metadata']['frame_basename'] = raw_basename
                    self.obs.enqueue_for_lco_archive(
                        filepath,
                        metadata=upload_metadata['image_metadata'],
                        is_thumbnail=True,
                    )
            else:
                mainjpegthread_filename='no'

            # Report files to the queues
            should_enqueue = (self.site_config['send_files_at_end_of_night'] == 'no' and
                              self.site_config['ingest_raws_directly_to_archive'])


            # Upload raw fits file to LCO archive
            if not is_osc and upload_metadata.get('is_lco_observation', False):
                filepath = f"{raw_path}{raw_name00}.fz"
                g_dev['obs'].enqueue_for_lco_archive(
                    filepath,
                    is_thumbnail=False,
                )


            # Upload raw fits to PTR archive
            if should_enqueue:
                filename = f"{raw_path}{raw_name00}.fz"
                if not is_osc:
                    # Single file for non-OSC
                    g_dev['obs'].enqueue_for_PTRarchive(26000000, '', filename)
                elif self.settings["osc_bayer"] == 'RGGB':
                    # For OSC with RGGB, upload each channel separately
                    for channel in ['R1', 'G1', 'G2', 'B1', 'CV']:
                        g_dev['obs'].enqueue_for_PTRarchive(
                            26000000, '',
                            filename.replace('-EX', f'{channel}-EX')
                        )
                else:
                        plog.warn("Failed to enqueue file for upload: unsupported bayer grid")
                        plog.warn(f"filename: {filename}, bayer type: {self.settings['osc_bayer']}")

            platesolvethread_filename='no'

            should_solve = (
                # Always solve if explicitly requested
                solve_it or

                # Otherwise, solve if any of these conditions are met:
                (not manually_requested_calibration and (
                    # Last image in a smartstack sequence (except single images)
                    ((Nsmartstack == sskcounter + 1) and Nsmartstack > 1) or

                    # Too many images since last solve
                    g_dev['obs'].images_since_last_solve > self.site_config["solve_nth_image"] or

                    # Too much time passed since last solve
                    #(datetime.now(tz=timezone.utc) - g_dev['obs'].last_solve_time) >
                    (datetime.utcnow() - g_dev['obs'].last_solve_time) >
                        timedelta(minutes=self.site_config["solve_timer"])
                ))
            )

            if should_solve:
                cal_name = cal_name[:-9] + "F012" + cal_name[-7:]

                # Check this is not an image in a smartstack set.
                # No shifts in pointing are wanted in a smartstack set!
                image_during_smartstack = False
                if Nsmartstack > 1 and not ((Nsmartstack == sskcounter+1) or sskcounter == 0):
                    image_during_smartstack = True
                if exposure_time < 1.0:
                    plog("Not doing Platesolve for sub-second exposures.")
                else:
                    if  (
                        solve_it or
                        (not image_during_smartstack and
                        not g_dev['seq'].currently_mosaicing and
                        not g_dev['obs'].pointing_correction_requested_by_platesolve_thread and
                        g_dev['obs'].platesolve_queue.empty() and
                        not g_dev['obs'].platesolve_is_processing)
                    ):

                        # # Make sure any dither or return nudge has finished before platesolution
                        if sskcounter == 0 and Nsmartstack > 1:
                            firstframesmartstack = True
                        else:
                            firstframesmartstack = False
                        platesolvethread_filename=self.local_calibration_path + "smartstacks/platesolve" + str(time.time()).replace('.','') + '.pickle'


                        g_dev['obs'].to_platesolve(
                            (
                                platesolvethread_filename,
                                'hdusmallheader',
                                cal_path,
                                cal_name,
                                frame_type,
                                time.time(),
                                self.pixscale,
                                ra_at_time_of_exposure,
                                dec_at_time_of_exposure,
                                firstframesmartstack,
                                useastrometrynet,
                                False,
                                jpeg_name, # filename
                                f'{im_path_r}{g_dev["day"]}/to_AWS/', #path to jpg directory
                                'reference',
                                exposure_time
                            )
                        )

                    else:
                        platesolvethread_filename='no'

        # The rest of this function is contained in this infinite loop
        while True:
            if time.time() < self.completion_time or self.async_exposure_lock:

                # Scan requests every 4 seconds... primarily hunting for a "Cancel/Stop"
                # and (time.time() - self.completion_time) > 4:
                if time.time() - exposure_scan_request_timer > 4:
                    exposure_scan_request_timer = time.time()

                    g_dev['obs'].request_scan_requests()

                    # Check there hasn't been a cancel sent through
                    if g_dev["obs"].stop_all_activity:
                        plog("stop_all_activity cancelling out of camera exposure")
                        Nsmartstack = 1
                        sskcounter = 2
                        expresult["error"] = True
                        expresult["stopped"] = True
                        g_dev["obs"].exposure_halted_indicator = False
                        self.running_an_exposure_set = False
                        self.currently_in_smartstack_loop = False
                        return expresult

                    if g_dev["obs"].exposure_halted_indicator:
                        expresult["error"] = True
                        expresult["stopped"] = True
                        g_dev["obs"].exposure_halted_indicator = False
                        self.running_an_exposure_set = False
                        plog("Exposure Halted Indicator On. Cancelling Exposure.")
                        return expresult

                remaining = round(self.completion_time - time.time(), 1)
                if remaining > 0:
                    if time.time() - self.plog_exposure_time_counter_timer > 10.0:
                        self.plog_exposure_time_counter_timer = time.time()
                        plog(
                            '||  ' + str(round(remaining, 1)) + "sec.",
                            str(round(100 * remaining / cycle_time, 1)) + "%",
                        )

                    if (
                        quartileExposureReport == 0
                    ):
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
                                g_dev['seq'].schedule_manager.update_now()
                            block_and_focus_check_done = True

                    # Need to have a time sleep to release the GIL to run the other threads
                    if time.time() > (self.start_time_of_observation + exposure_time):
                        # If the exposure time has passed, then the shutter is closed for normal exposures
                        # The substacker thread reports the shutter_open(/closed). Other methods may not.
                        if not substack:
                            self.shutter_open=False

                    # If the shutter has closed but there is still time, then nudge the scope while reading out
                    if not self.shutter_open:

                        # Attempt to sneak in a platesolve and nudge during readout time.
                        if not check_nudge_after_shutter_closed:
                            # Deleted the "Shutter" mis-que.
                            plog("Readout Complete.")
                            # Immediately nudge scope to a different point in the smartstack dither except for the last frame and after the last frame.
                            if not g_dev['obs'].mountless_operation:
                                if g_dev['seq'].flats_being_collected:
                                    # Check if this is a moment where the scope should be nudged and the filter changed.
                                    # If the previous shot was successful, then we assume this one is and just
                                    # cut to the chase and nudge the mount as early as possible.
                                    # If you got a successful flat in the last exposure
                                    if g_dev['seq'].got_a_flat_this_round:
                                        # And it is the last exposure of the set of flats for that filter.
                                        if g_dev['seq'].last_image_of_a_filter_flat_set:
                                            # Nudge the scope
                                            g_dev['seq'].check_zenith_and_move_to_flat_spot(
                                                ending=g_dev['seq'].flats_ending, dont_wait_after_slew=True)
                                            g_dev['seq'].time_of_next_slew = time.time(
                                            ) + 600
                                            g_dev['seq'].scope_already_nudged_by_camera_thread = True
                                            # Swap the filter
                                            if not null_filterwheel:
                                                if g_dev['seq'].next_filter_in_flat_run != 'none':
                                                    self.current_filter, filter_number, filter_offset = fw_device.set_name_command(
                                                        {"filter": g_dev['seq'].next_filter_in_flat_run}, {
                                                        }
                                                    )

                                elif g_dev['obs'].pointing_recentering_requested_by_platesolve_thread or g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                                    if not  g_dev['obs'].auto_centering_off:
                                        g_dev['obs'].check_platesolve_and_nudge()

                                # Don't nudge scope if it wants to correct the pointing or is slewing or there has been a pier flip or parked.
                                elif self.dither_enabled and not g_dev['mnt'].pier_flip_detected and not g_dev['mnt'].currently_slewing and not g_dev['mnt'].rapid_park_indicator and not g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                                    if Nsmartstack > 1 and not ((Nsmartstack == sskcounter+1) or (Nsmartstack == sskcounter+2)):
                                        if (self.pixscale == None):
                                            ra_random_dither = (
                                                ((random.randint(0, 50)-25) * 0.75 / 3600) / 15)
                                            dec_random_dither = (
                                                (random.randint(0, 50)-25) * 0.75 / 3600)
                                        else:
                                            ra_random_dither = (
                                                ((random.randint(0, 50)-25) * self.pixscale / 3600) / 15)
                                            dec_random_dither = (
                                                (random.randint(0, 50)-25) * self.pixscale / 3600)
                                        try:
                                            # g_dev['mnt'].wait_for_slew(wait_after_slew=False)
                                            g_dev['mnt'].slew_async_directly(
                                                ra=self.initial_smartstack_ra + ra_random_dither, dec=self.initial_smartstack_dec + dec_random_dither)

                                        except Exception as e:
                                            plog(traceback.format_exc())
                                            if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:
                                                plog("The SkyX had an error.")
                                                plog(
                                                    "Usually this is because of a broken connection.")
                                                plog(
                                                    "Killing then waiting 60 seconds then reconnecting")
                                                g_dev['obs'].kill_and_reboot_theskyx(
                                                    g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec)

                                    # Otherwise immediately nudge scope back to initial pointing in smartstack after the last frame of the smartstack
                                    # Last frame of the smartstack must also be at the normal pointing for platesolving purposes
                                    elif Nsmartstack > 1 and ((Nsmartstack == sskcounter+1) or (Nsmartstack == sskcounter+2)):
                                        try:
                                            g_dev['mnt'].slew_async_directly(ra=self.initial_smartstack_ra, dec=self.initial_smartstack_dec)
                                        except Exception as e:
                                            plog(traceback.format_exc())
                                            if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:
                                                plog("The SkyX had an error.")
                                                plog(
                                                    "Usually this is because of a broken connection.")
                                                plog(
                                                    "Killing then waiting 60 seconds then reconnecting")
                                                g_dev['obs'].kill_and_reboot_theskyx(
                                                    g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec)

                            # If this is the last set of something in an execute_block from the sequence (project calendar)
                            # Then get ready for the next set of exposures by changing the filter and adjusting the focus
                            # Hopefully this occurs while the slew occurs
                            # If there is a block guard, there is a running block
                            if g_dev['seq'].block_guard and not g_dev['seq'].focussing and not frame_type == 'pointing' and not frame_type == 'skyflat':
                                # If this is the end of a smartstack set or it is a single shot then check the filter and change
                                if Nsmartstack == 1 or (Nsmartstack == sskcounter+1):
                                    plog("Next filter in project: " +
                                         str(g_dev['seq'].block_next_filter_requested))
                                    plog("Current filter: " +
                                         str(self.current_filter))
                                    if not g_dev['seq'].block_next_filter_requested == 'None':
                                        # Check if filter needs changing, if so, change.
                                        self.current_filter = fw_device.current_filter_name
                                        if not self.current_filter == g_dev['seq'].block_next_filter_requested:
                                            plog("Changing filter")
                                            self.current_filter, filter_number, filter_offset = fw_device.set_name_command(
                                                {"filter": g_dev['seq'].block_next_filter_requested}, {
                                                }
                                            )

                            check_nudge_after_shutter_closed = True

                        temp_time_sleep = min(
                            self.completion_time - time.time() + 0.00001,
                            initialRemaining * 0.125
                        )

                    else:
                        if time.time() < (self.start_time_of_observation + exposure_time):
                            temp_time_sleep = min(
                                self.start_time_of_observation + exposure_time - time.time() + 0.00001,
                                initialRemaining * 0.125
                            )

                    if temp_time_sleep > 0:
                        time.sleep(temp_time_sleep)
                continue

            elif self.async_exposure_lock == False and self._imageavailable():

                if self.shutter_open:
                    self.shutter_open = False
                    plog("Light Gathering Complete.")

                plog("Readout Complete")

                # post_overhead_timer = time.time()



                # Good spot to check if we need to nudge the telescope
                # Allowed to on the last loop of a smartstack
                # We need to clear the nudge before putting another platesolve in the queue
                if (Nsmartstack > 1 and (Nsmartstack == sskcounter+1)):
                    self.currently_in_smartstack_loop=False

                # If the nudge wasn't done during the readout, then nudge it now
                if not check_nudge_after_shutter_closed:
                    # Immediately nudge scope to a different point in the smartstack dither except for the last frame and after the last frame.
                    if not g_dev['obs'].mountless_operation:
                        if g_dev['obs'].pointing_recentering_requested_by_platesolve_thread or g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                           if not  g_dev['obs'].auto_centering_off:
                               g_dev['obs'].check_platesolve_and_nudge()

                        # Don't nudge scope if it wants to correct the pointing or is slewing or there has been a pier flip.
                        elif self.dither_enabled and not g_dev['mnt'].pier_flip_detected and not g_dev['mnt'].currently_slewing and not g_dev['mnt'].rapid_park_indicator and not g_dev['obs'].pointing_correction_requested_by_platesolve_thread:
                            if Nsmartstack > 1 and not ((Nsmartstack == sskcounter+1) or (Nsmartstack == sskcounter+2)):
                                if (self.pixscale == None):
                                    ra_random_dither = (
                                        ((random.randint(0, 50)-25) * 0.75 / 3600) / 15)
                                    dec_random_dither = (
                                        (random.randint(0, 50)-25) * 0.75 / 3600)
                                else:
                                    ra_random_dither = (
                                        ((random.randint(0, 50)-25) * self.pixscale / 3600) / 15)
                                    dec_random_dither = (
                                        (random.randint(0, 50)-25) * self.pixscale / 3600)
                                try:
                                    g_dev['mnt'].slew_async_directly(ra=self.initial_smartstack_ra + ra_random_dither, dec=self.initial_smartstack_dec + dec_random_dither)

                                except Exception as e:
                                    plog(traceback.format_exc())
                                    if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:
                                        plog("The SkyX had an error.")
                                        plog(
                                            "Usually this is because of a broken connection.")
                                        plog(
                                            "Killing then waiting 60 seconds then reconnecting")
                                        g_dev['obs'].kill_and_reboot_theskyx(
                                            g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec)

                            # Otherwise immediately nudge scope back to initial pointing in smartstack after the last frame of the smartstack
                            # Last frame of the smartstack must also be at the normal pointing for platesolving purposes
                            elif Nsmartstack > 1 and ((Nsmartstack == sskcounter+1) or (Nsmartstack == sskcounter+2)):
                                try:
                                    # g_dev['mnt'].wait_for_slew(wait_after_slew=False)
                                    g_dev['mnt'].slew_async_directly(
                                        ra=self.initial_smartstack_ra, dec=self.initial_smartstack_dec)

                                except Exception as e:
                                    plog(traceback.format_exc())
                                    if 'Object reference not set' in str(e) and g_dev['mnt'].theskyx:
                                        plog("The SkyX had an error.")
                                        plog(
                                            "Usually this is because of a broken connection.")
                                        plog(
                                            "Killing then waiting 60 seconds then reconnecting")
                                        g_dev['obs'].kill_and_reboot_theskyx(
                                            g_dev['mnt'].current_icrs_ra, g_dev['mnt'].current_icrs_dec)

                    # If this is the last set of something in an execute_block from the sequence (project calendar)
                    # Then get ready for the next set of exposures by changing the filter and adjusting the focus
                    # Hopefully this occurs while the slew occurs
                    # If there is a block guard, there is a running block
                    if g_dev['seq'].block_guard and not g_dev['seq'].focussing and not frame_type == 'pointing' and not g_dev['seq'].currently_mosaicing:
                        # If this is the end of a smartstack set or it is a single shot then check the filter and change
                        if (Nsmartstack == 1 or (Nsmartstack == sskcounter+1)):
                            if hasattr(g_dev['seq'], 'block_next_filter_requested') and g_dev['seq'].block_next_filter_requested != 'None':
                                # Check if filter needs changing, if so, change.
                                self.current_filter = fw_device.current_filter_name
                                if not self.current_filter.lower() == g_dev['seq'].block_next_filter_requested.lower():
                                    plog(
                                        "Changing filter for next smartstack round.")
                                    self.current_filter, filter_number, filter_offset = fw_device.set_name_command(
                                        {"filter": g_dev['seq'].block_next_filter_requested}, {
                                        }
                                    )

                if not frame_type in (
                        "flat",
                        "screenflat",
                        "skyflat"):
                    g_dev["obs"].send_to_user("Exposure Complete")

                if self.theskyx:
                    self.readout_estimate = time.time() - self.start_time_of_observation - exposure_time

                if substack:
                    expected_endpoint_of_substack_exposure=copy.deepcopy(self.expected_endpoint_of_substack_exposure)
                    substack_start_time=copy.deepcopy(self.substack_start_time)
                    sub_stacker_midpoints=copy.deepcopy(self.sub_stacker_midpoints)
                else:
                    expected_endpoint_of_substack_exposure = None
                    substack_start_time = None
                    sub_stacker_midpoints = None

                # HERE WE EITHER GET THE IMAGE ARRAY OR REPORT THE SUBSTACKER ARRAY

                if substack:
                    outputimg='substacker'
                else:
                    imageCollected = 0
                    retrycounter = 0
                    while imageCollected != 1:
                        if retrycounter == 8:
                            expresult = {"error": True}
                            plog("Retried 8 times and didn't get an image, giving up.")
                            return expresult
                        try:
                            outputimg = self._getImageArray()  # .astype(np.float32)
                            imageCollected = 1

                            if True:
                               height, width = outputimg.shape
                               patch = outputimg[int(0.4*height):int(0.6*height), int(0.4*width):int(0.6*width)]
                               plog(">>>>  20% central image patch, std:  ", bn.nanmedian(patch), round(bn.nanstd(patch), 2), str(width)+'x'+str(height) )

                            if False:
                                # If this is set to true, then it will output a sample of the image.
                                hdufocus = fits.PrimaryHDU()
                                hdufocus.data = outputimg
                                # hdufocus.header = hdu.header
                                # hdufocus.header["NAXIS1"] = hdu.data.shape[0]
                                # hdufocus.header["NAXIS2"] = hdu.data.shape[1]
                                hdufocus.writeto(cal_path + 'rawdump.fits', overwrite=True, output_verify='silentfix')


                        except Exception as e:

                            if self.theskyx:
                                if 'No such file or directory' in str(e):
                                    plog(
                                        "Found rare theskyx bug in image acquisition, rebooting and killing theskyx.... or the other way around.")
                                    plog(e)
                                    plog(traceback.format_exc())
                                    g_dev['obs'].kill_and_reboot_theskyx(
                                        g_dev['mnt'].return_right_ascension(), g_dev['mnt'].return_declination())

                                    expresult = {}
                                    expresult["error"] = True
                                    return expresult
                            else:
                                plog(e)
                                plog(traceback.format_exc())
                                if "Image Not Available" in str(e):
                                    plog("Still waiting for file to arrive: ", e)
                            time.sleep(3)
                            retrycounter = retrycounter + 1


                ################################################# CUTOFF FOR THE POSTPROCESSING QUEUE

################################ START OFF THE MAIN POST_PROCESSING SUBTHREAD

                if not frame_type[-4:] == "flat" and not frame_type in ["bias", "dark"]  and not a_dark_exposure and not focus_image and not frame_type=='pointing':
                    if substack:
                        outputimg=''

                    if g_dev['obs'].mountless_operation:
                        pier_side=0
                        ha_corr=0
                        dec_corr=0
                    else:
                        pier_side=g_dev["mnt"].pier_side
                        ha_corr=g_dev["mnt"].ha_corr
                        dec_corr=g_dev["mnt"].dec_corr


                    # Is exposure in nightime?
                    now = ephem.Date(ephem.now())
                    observing_ends = self.obs.events['Observing Ends']
                    observing_begins = self.obs.events['Observing Begins']



                    if  now < observing_begins or  now > observing_ends:
                        exposure_in_nighttime=False
                    else:
                        exposure_in_nighttime=True



                    post_exposure_subprocess_inputs = {
                        "image_data": {
                            "outputimg": outputimg,
                            "substacker_filenames": self.substacker_filenames,
                            "sub_stacker_midpoints": sub_stacker_midpoints,
                            "unique_batch_code": unique_batch_code
                        },
                        "camera_settings": {
                            "is_osc": self.settings['is_osc'],
                            "pixscale": self.pixscale,
                            "camera_device_name": self.name,
                            "camera_known_gain": self.camera_known_gain,
                            "camera_known_readnoise": self.camera_known_readnoise,
                            "camera_path": self.camera_path,
                            "setpoint": self.setpoint,
                            "tempccdtemp": self.tempccdtemp,
                            "ccd_humidity": self.ccd_humidity,
                            "ccd_pressure": self.ccd_pressure,
                            "darkslide_state": self.darkslide_state,
                            "readout_time": self.readout_time,
                            "readout_estimate": 0.0
                        },
                        "exposure_details": {
                            "exposure_time": exposure_time,
                            "frame_type": frame_type,
                            "this_exposure_filter": this_exposure_filter,
                            "exposure_filter_offset": exposure_filter_offset,
                            "null_filterwheel": null_filterwheel,
                            "start_time_of_observation": self.start_time_of_observation,
                            "number_of_exposures_requested": count,
                            "manually_requested_calibration": manually_requested_calibration,
                            "next_seq": next_seq
                        },
                        "instrument_info": {
                            "pier_side": pier_side,
                            "avg_mnt": avg_mnt,
                            "avg_foc": avg_foc,
                            "avg_rot": avg_rot,
                            "focus_position": focus_position,
                            "azimuth_of_observation": azimuth_of_observation,
                            "altitude_of_observation": altitude_of_observation,
                            "airmass_of_observation": airmass_of_observation,
                            "ra_at_time_of_exposure": ra_at_time_of_exposure,
                            "dec_at_time_of_exposure": dec_at_time_of_exposure,
                            "corrected_ra_for_header": corrected_ra_for_header,
                            "corrected_dec_for_header": corrected_dec_for_header,
                            "ha_corr": ha_corr,
                            "dec_corr": dec_corr
                        },
                        "target_info": {
                            "object_name": object_name,
                            "object_specf": object_specf
                        },
                        "observer_info": {
                            "observer_user_name": observer_user_name,
                            "observer_user_id": observer_user_id,
                            "optional_params": optional_params
                        },
                        "stack_info": {
                            "smartstackid": smartstackid,
                            "sskcounter": sskcounter,
                            "Nsmartstack": Nsmartstack,
                            "zoom_factor": zoom_factor,
                            "substack": substack,
                            "expected_endpoint_of_substack_exposure": expected_endpoint_of_substack_exposure,
                            "substack_start_time": substack_start_time
                        },
                        "config_settings": {
                            "site_config": self.site_config,
                            "wema_config": self.obs.wema_config,
                            "day_directory": self.obs.events.get('day_directory')
                        },
                        "thread_files": {
                            "smartstackthread_filename": smartstackthread_filename,
                            "photometry_thread_filename": photometry_thread_filename,
                            "mainjpegthread_filename": mainjpegthread_filename,
                            "platesolvethread_filename": platesolvethread_filename
                        },
                        "other": {
                            "exposure_in_nighttime": exposure_in_nighttime
                        },
                        "lco_header_data": upload_metadata.get('image_metadata')
                    }

                    # It actually takes a few seconds to spin up the main subprocess, so we farm this out to a thread
                    # So the code can continue more quickly to the next exposure.
                    thread = threading.Thread(target=dump_main_data_out_to_post_exposure_subprocess, args=(post_exposure_subprocess_inputs, post_processing_subprocess,))
                    thread.daemon = True
                    thread.start()


################################################# HERE IS WHERE IN-LINE STUFF HAPPENS.


                # BIAS & DARK, flat, focus and pointing VETTING AND DISTRIBUTION AREA.

                # For biases, darks, flats, focus and pointing images, it doesn't go to the subprocess.
                # It either doesn't buy us any time OR the results of one image relies on the next....
                # e.g. the next flat exposure relies on the throughput results of the last
                # or a focus exposure has a logic about whether it has successfully focussed or not
                # So this is done in the main thread. Whereas normal exposures get done in the subprocess.
                if (frame_type in ["bias", "dark"] or a_dark_exposure or frame_type[-4:] == ['flat']) and not manually_requested_calibration:
                    plog("Median of full-image area bias, dark or flat:  ",
                         round(bn.nanmedian(outputimg), 2), round(bn.nanstd(outputimg), 3))

                    # Check that the temperature is ok before accepting
                    current_camera_temperature, cur_humidity, cur_pressure, cur_pwm = (
                        self._temperature())
                    current_camera_temperature = float(
                        current_camera_temperature)
                    # NB NB this might best be a config item.
                    if abs(current_camera_temperature - float(self.setpoint)) > self.temp_tolerance:
                        plog("temperature out of range for calibrations (" +
                             str(current_camera_temperature)+"), rejecting calibration frame")
                        g_dev['obs'].camera_sufficiently_cooled_for_calibrations = False
                        expresult = {}
                        expresult["error"] = True
                        return expresult
                    else:
                        plog("temperature in range for calibrations (" +
                             str(current_camera_temperature)+"), accepting calibration frame")
                        g_dev['obs'].camera_sufficiently_cooled_for_calibrations = True

                    # Really need to thresh the image
                    unique,counts=np.unique(outputimg.ravel()[~np.isnan(outputimg.ravel())].astype(int), return_counts=True)
                    m=counts.argmax()
                    imageMode=unique[m]

                    histogramdata=np.column_stack([unique,counts]).astype(np.int32)
                    histogramdata[histogramdata[:,0] > -10000]
                    #Do some fiddle faddling to figure out the value that goes to zero less
                    zeroValueArray = histogramdata[histogramdata[:, 0] < imageMode]
                    zerocounter = 0
                    while True:
                        zerocounter += 1
                        if all((imageMode - zerocounter - offset) not in zeroValueArray[:, 0] for offset in range(17)):
                            zeroValue = imageMode - zerocounter
                            break
                    countypixels=outputimg[ np.where(outputimg < zeroValue ) ]
                    plog ("Number of unnaturally negative pixels: " + str(len(countypixels)) )
                    plog ("Next seq:  ", next_seq)
                    del unique
                    del counts


                    # If there are too many unnaturally negative pixels, then reject the calibration
                    if len(countypixels) > 50000:  #Up from 100 for 100 megapix camera
                        plog(
                            "Rejecting calibration because it has a high amount of low value pixels." + str(len(countypixels)) + " !!!!!!!!!!!!!!!!!")
                        expresult = {}
                        expresult["error"] = True
                        #breakpoint()
                        return expresult

                    # For a dark, check that the debiased dark has an adequately low value
                    # If there is no master bias, it will just skip this check
                    if frame_type in ["dark"] or a_dark_exposure:
                        dark_limit_adu = self.settings['dark_lim_adu']
                        if len(self.biasFiles) > 0:
                            tempcrop = int(min(outputimg.shape)*0.15)

                            tempmodearray = ((outputimg[tempcrop:-tempcrop, tempcrop:-tempcrop] - self.biasFiles[str(
                                1)][tempcrop:-tempcrop, tempcrop:-tempcrop]) * 10)
                            int_array_flattened = tempmodearray.astype(
                                int).ravel()
                            unique, counts = np.unique(
                                int_array_flattened[~np.isnan(int_array_flattened)], return_counts=True)
                            m = counts.argmax()
                            imageMode = unique[m]
                            del unique
                            del counts
                            del int_array_flattened
                            del tempmodearray

                            debiaseddarkmode = round(imageMode / 10 / exposure_time, 4)

                            plog("Debiased 1s Dark Mode is " +
                                 str(debiaseddarkmode))

                            debiaseddarkmedian = round(bn.nanmedian(outputimg[tempcrop:-tempcrop, tempcrop:-tempcrop] - self.biasFiles[str(
                                1)][tempcrop:-tempcrop, tempcrop:-tempcrop]) / exposure_time, 4)
                            plog("Debiased 1s Dark Median is " +
                                 str(debiaseddarkmedian))

                            debiaseddarkmean = round(bn.nanmean(outputimg[tempcrop:-tempcrop, tempcrop:-tempcrop] - self.biasFiles[str(
                                1)][tempcrop:-tempcrop, tempcrop:-tempcrop]) / exposure_time, 4)
                            plog("Debiased 1s Dark Mean is " + str(debiaseddarkmean))


                            plog ("Exposure time: " + str(exposure_time))

                            #Short exposures are inherently much more variable, so their limit is set much higher.
                            if not g_dev['seq'].check_incoming_darks_for_light_leaks:
                                plog ("Light Leak checks for darks turned off, usually for a new batch of darks.")
                            elif frame_type in ['fortymicrosecond_exposure_dark', 'fourhundredmicrosecond_exposure_dark','pointzerozerofourfive_exposure_dark','onepointfivepercent_exposure_dark','fivepercent_exposure_dark','tenpercent_exposure_dark']:
                                plog ("This exposure is too short for the dark rejecter to be particularly reliable.")
                            elif frame_type in ['quartersec_exposure_dark', 'halfsec_exposure_dark','threequartersec_exposure_dark','onesec_exposure_dark', 'oneandahalfsec_exposure_dark', 'twosec_exposure_dark']:
                                if debiaseddarkmedian > 10*dark_limit_adu:
                                    plog ("Reject! This Dark seems to be light affected. ")
                                    expresult = {}
                                    expresult["error"] = True
                                    return expresult
                            elif debiaseddarkmedian > dark_limit_adu:
                                plog ("Reject! This Dark seems to be light affected. ")
                                expresult = {}
                                expresult["error"] = True
                                return expresult

                # Specific dark and bias save area
                if (frame_type in ["bias", "dark"] or a_dark_exposure) and not manually_requested_calibration:

                    im_path_r = self.camera_path
                    raw_path = im_path_r + g_dev["day"] + "/raw/"

                    raw_name00 = (
                        obs_id
                        + "-"
                        + self.alias + '_' +
                        str(frame_type.replace('_', '')) +
                        '_' + str(this_exposure_filter)
                        + "-"
                        + g_dev["day"]
                        + "-"
                        + next_seq
                        + "-"
                        + "calibration"
                        + "frame.fits"
                    )

                    hdu = fits.PrimaryHDU()
                    hdu = fits.PrimaryHDU(
                        outputimg.astype('float32')
                    )
                    del outputimg
                    try:
                        hdu.header['PIXSCALE'] = self.pixscale
                    except:
                        hdu.header['PIXSCALE'] = -99
                    hdu.header['EXPTIME'] = exposure_time
                    hdu.header['OBSTYPE'] = 'flat'
                    hdu.header['FILTER'] = this_exposure_filter
                    hdu.header["DAY-OBS"] = (
                        g_dev["day"],
                        "Date at start of observing night"
                    )    #NB Added this in just now, reported missing by injester.  20250112 WER  Not sure this is the right place to add this in.

                    # If the files are local calibrations, save them out to the local calibration directory
                    if not manually_requested_calibration:
                        if not g_dev['obs'].mountless_operation:
                            g_dev['obs'].to_slow_process(200000000, ('localcalibration', copy.deepcopy(raw_name00), copy.deepcopy(hdu.data), copy.deepcopy(
                                hdu.header), copy.deepcopy(frame_type), copy.deepcopy(g_dev["mnt"].current_icrs_ra), copy.deepcopy(g_dev["mnt"].current_icrs_dec), current_camera_temperature))
                        else:
                            g_dev['obs'].to_slow_process(200000000, ('localcalibration', copy.deepcopy(raw_name00), copy.deepcopy(
                                hdu.data), copy.deepcopy(hdu.header), copy.deepcopy(frame_type), None, None,current_camera_temperature))

                    # Make  sure the alt paths exist
                    if g_dev['obs'].config["save_to_alt_path"] == "yes":
                        altpath = copy.deepcopy(g_dev['obs'].alt_path)
                    else:
                        altpath = 'no'

                    # Similarly to the above. This saves the RAW file to disk
                    if self.site_config['save_raw_to_disk']:

                        # Make sure the raw paths exist
                        im_path_r = self.camera_path
                        raw_path = im_path_r + g_dev["day"] + "/raw/"
                        os.makedirs(
                            self.camera_path + g_dev["day"], exist_ok=True, mode=0o777
                        )

                        os.makedirs(
                            raw_path, exist_ok=True, mode=0o777
                        )


                        thread = threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw', raw_path + raw_name00, hdu.data, hdu.header,
                                         frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec, altpath, 'deprecated')),))
                        thread.daemon = True
                        thread.start()

                    # For sites that have "save_to_alt_path" enabled, this routine
                    # Saves the raw and reduced fits files out to the provided directories
                    if self.site_config["save_to_alt_path"] == "yes":
                        self.alt_path = self.site_config[
                            "alt_path"
                        ] + '/' + obs_id + '/'

                        os.makedirs(
                            self.alt_path, exist_ok=True, mode=0o777
                        )

                        os.makedirs(
                            self.alt_path + g_dev["day"], exist_ok=True, mode=0o777
                        )

                        os.makedirs(
                            self.alt_path + g_dev["day"] + "/raw/", exist_ok=True, mode=0o777
                        )
                        thread = threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw_alt_path', self.alt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header,
                                                                                        frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec, altpath, 'deprecated')),))
                        thread.daemon = True
                        thread.start()

                    del hdu
                    return copy.deepcopy(expresult)

                # IN-LINE REDUCED FRAMES (POINTING AND FOCUS) AREA

                # If this is a pointing or a focus frame, we need to do an
                # in-line flash reduction
                if (frame_type == 'pointing' or focus_image == True) and not substack:
                    # Make sure any dither or return nudge has finished before platesolution

                    try:
                        # If not a smartstack use a scaled masterdark
                        if smartstackid == 'no':
                            # Initially debias the image
                            outputimg = outputimg - \
                                self.biasFiles[str(1)]
                            outputimg = outputimg - \
                                (intermediate_tempdark*exposure_time)
                            del intermediate_tempdark
                        elif exposure_time == broadband_ss_biasdark_exp_time:
                            outputimg = outputimg - \
                                (self.darkFiles['broadband_ss_biasdark'])
                        elif exposure_time == narrowband_ss_biasdark_exp_time:
                            outputimg = outputimg - \
                                (self.darkFiles['narrowband_ss_biasdark'])
                        else:
                            plog("DUNNO WHAT HAPPENED!")
                            outputimg = outputimg - \
                                self.biasFiles[str(1)]
                            outputimg = outputimg - \
                                (self.darkFiles[str(1)] * exposure_time)
                    except Exception as e:
                        plog("debias/darking light frame failed: ", e)

                    # Quick flat flat frame
                    try:
                        outputimg = np.divide(outputimg, intermediate_tempflat)
                    except Exception as e:
                        plog("flatting light frame failed", e)

                    try:
                        outputimg[self.bpmFiles[str(1)]] = np.nan
                    except Exception as e:
                        plog("applying bad pixel mask to light frame failed: ", e)

                    # # Thresh the image
                    # # Really need to thresh the image
                    # unique,counts=np.unique(outputimg.ravel()[~np.isnan(outputimg.ravel())].astype(int), return_counts=True)
                    # m=counts.argmax()
                    # imageMode=unique[m]

                    # histogramdata=np.column_stack([unique,counts]).astype(np.int32)
                    # histogramdata[histogramdata[:,0] > -10000]
                    # #Do some fiddle faddling to figure out the value that goes to zero less
                    # zeroValueArray = histogramdata[histogramdata[:, 0] < imageMode]
                    # zerocounter = 0
                    # while True:
                    #     zerocounter += 1
                    #     if all((imageMode - zerocounter - offset) not in zeroValueArray[:, 0] for offset in range(17)):
                    #         zeroValue = imageMode - zerocounter
                    #         break
                    # outputimg[outputimg < zeroValue] = np.nan


                if frame_type=='pointing' and focus_image == False:

                    hdu = fits.PrimaryHDU()

                    if self.pixscale == None: # np.isnan(self.pixscale) or
                        plog("no pixelscale available")
                        hdu.header['PIXSCALE'] = 'unknown'
                    else:
                        hdu.header['PIXSCALE'] = self.pixscale

                    hdu.header['OBSTYPE'] = 'pointing'
                    hdusmallheader = copy.deepcopy(hdu.header)
                    del hdu

                    g_dev['obs'].platesolve_is_processing =True
                    g_dev['obs'].to_platesolve(
                        (
                            np.maximum(outputimg, 0).astype(np.uint16),
                            hdusmallheader,
                            cal_path,
                            cal_name,
                            frame_type,
                            time.time(),
                            self.pixscale,
                            ra_at_time_of_exposure,
                            dec_at_time_of_exposure,
                            False,
                            useastrometrynet,
                            True,
                            jpeg_name, # filename
                            f'{im_path_r}{g_dev["day"]}/to_AWS/', #path to jpg directory
                            'image',
                            exposure_time
                        )
                   )

                # If this is a focus image,
                # FWHM.
                if focus_image == True:

                    hdu = fits.PrimaryHDU()
                    try:
                        hdu.header['PIXSCALE'] = self.pixscale
                    except:
                        hdu.header['PIXSCALE'] = -99
                    hdu.header['EXPTIME'] = exposure_time

                    hdu.header['OBSTYPE'] = 'focus'
                    hdu.header["SITEID"] = (
                        self.site_config["wema_name"].replace("-", "").replace("_", ""))
                    hdu.header["INSTRUME"] = (
                        self.alias, "Name of camera")
                    hdu.header["DAY-OBS"] = (
                        g_dev["day"],
                        "Date at start of observing night"
                    )

                    hdu.header["ORIGNAME"] = str(raw_name00 + ".fz")
                    hdu.header["FILTER"] = this_exposure_filter
                    hdu.header["SMARTSTK"] = 'no'
                    hdu.header["SSTKNUM"] = 1
                    hdu.header["SUBSTACK"] = substack

                    tempRAdeg = ra_at_time_of_exposure * 15
                    tempDECdeg = dec_at_time_of_exposure
                    tempointing = SkyCoord(tempRAdeg, tempDECdeg, unit='deg')
                    tempointing = tempointing.to_string("hmsdms").split(' ')

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
                    hdu.header["ZENITH"] = (
                        90 - altitude_of_observation, "[deg] Zenith")
                    hdu.header["AIRMASS"] = (
                        airmass_of_observation,
                        "Effective mean airmass",
                    )

                    hdusmallheader = copy.deepcopy(hdu.header)
                    del hdu
                    focus_position = g_dev['foc'].current_focus_position

                    try:
                        # Cut down focus image to central degree
                        fx, fy = outputimg.shape
                        # We want a standard focus image size that represent 0.2 degrees - which is the size of the focus fields.
                        # However we want some flexibility in the sense that the pointing could be off by half a degree or so...
                        # So we chop the image down to a degree by a degree
                        # This speeds up the focus software.... we don't need to solve for EVERY star in a widefield image.
                        if self.pixscale == None:
                            # # If we don't know the pixelscale, we don't know the size, but 1000 x 1000 should be big enough!!
                            # # Get the current dimensions
                            # height, width = outputimg.shape[:2]

                            # # Determine cropping bounds
                            # new_height = min(height, 3000)
                            # new_width = min(width, 3000)

                            # # Calculate start indices to center-crop
                            # start_y = (height - new_height) // 2
                            # start_x = (width - new_width) // 2

                            # # Crop the image
                            # outputimg = outputimg[start_y:start_y + new_height, start_x:start_x + new_width]
                            pass
                        else:

                            fx_degrees = (fx * self.pixscale) / 3600
                            fy_degrees = (fy * self.pixscale) / 3600
                            crop_x = 0
                            crop_y = 0
                            if fx_degrees > 1.0:
                                ratio_crop = 1/fx_degrees
                                crop_x = int((fx - (ratio_crop * fx))/2)
                            if fy_degrees > 1.0:
                                ratio_crop = 1/fy_degrees
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
                                outputimg = outputimg[crop_x:-crop_x, crop_y:-crop_y]

                        if self.is_osc:

                            outputimg=block_reduce(outputimg,2)

                        # Really need a nice clean image to do this.
                        googtime=time.time()
                        # 1) pick your subsampling factor
                        ny, nx = outputimg.shape
                        total_px = ny * nx
                        if total_px > 100_000_000:
                            subs = 10
                        elif total_px >  50_000_000:
                            subs = 5
                        else:
                            subs = 2

                        # 2) grab the strided‐subsample
                        sample = outputimg[::subs, ::subs]

                        # 3) compute mode on the sample
                        vals = sample.ravel()
                        vals = vals[np.isfinite(vals)].astype(np.int32)
                        unique, counts = np.unique(vals, return_counts=True)
                        m = counts.argmax()
                        imageMode = unique[m]
                        # plog(f"Calculating Mode (subs={subs}): {time.time()-googtime:.3f} s")

                        # 4) now build the histogramdata (so we still have unique & counts)
                        histogramdata = np.column_stack([unique, counts]).astype(np.int32)
                        # optional filter your histogram (you had this line, though it doesn't assign)
                        histogramdata = histogramdata[histogramdata[:,0] > -10000]

                        # 5) find the highest “gap” below imageMode
                        zeroValueArray = histogramdata[histogramdata[:,0] < imageMode, 0]
                        zerocounter = 0
                        while True:
                            zerocounter += 1
                            test = imageMode - zerocounter
                            # look for a run of 17 empty bins below the mode
                            if all(((test - offset) not in zeroValueArray) for offset in range(17)):
                                zeroValue = test
                                break

                        # 6) apply your zero‐threshold
                        outputimg[outputimg < zeroValue] = np.nan
                        del unique
                        del counts

                        #If it is a focus image then it will get sent in a different manner to the UI for a jpeg
                        # In this case, the image needs to be the 0.2 degree field that the focus field is made up of
                        hdusmalldata = np.array(outputimg)
                        fx, fy = hdusmalldata.shape

                        aspect_ratio= fx/fy
                        if self.pixscale == None:
                            focus_jpeg_size=500
                        else:
                            focus_jpeg_size=0.2/(self.pixscale/3600)
                        if focus_jpeg_size < fx:
                            crop_width = (fx - focus_jpeg_size) / 2
                        else:
                            crop_width =2

                        if focus_jpeg_size < fy:
                            crop_height = (fy - (focus_jpeg_size / aspect_ratio)) / 2
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
                            hdusmalldata = hdusmalldata[crop_width:-
                                                        crop_width, crop_height:-crop_height]

                        hdusmalldata = hdusmalldata - bn.nanmin(hdusmalldata)

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

                        if iy == ix:
                            final_image = final_image.resize(
                                (900, 900)
                            )
                        else:
                            final_image = final_image.resize(
                                (900, int(900 * iy / ix))
                            )

                        self.current_focus_jpg = copy.deepcopy(final_image)

                        # Image is now a degree on a side or less, but now lets deal with
                        # unnecessary pixelscale
                        temp_focus_bin=1
                        if not self.pixscale == None:
                            if self.pixscale < 0.3:
                                outputimg=block_reduce(outputimg,3)
                                temp_focus_bin=3
                            elif self.pixscale < 0.6:
                                temp_focus_bin=2
                                outputimg=block_reduce(outputimg,2)
                            # else:


                        # Here we decide if Fwe are using source-extractor++
                        # Which is great for actual focussing as it is quite robust
                        # to blobs and donuts or whether we are using the gaussian method
                        # which gives a quite accurate estimate of the true fwhm
                        # from this scope

                        do_source_extractor=True
                        if frame_type == 'focus_confirmation':
                            do_source_extractor=False

                        if do_source_extractor:# and not detected_donuts:
                            try:
                                # Utilise smartstacks directory as it is a temp directory that gets cleared out
                                tempdir=self.local_calibration_path + "smartstacks/"
                                tempdir_in_wsl=tempdir.split(':')
                                tempdir_in_wsl[0]=tempdir_in_wsl[0].lower()
                                tempdir_in_wsl='/mnt/'+ tempdir_in_wsl[0] + tempdir_in_wsl[1]
                                tempdir_in_wsl=tempdir_in_wsl.replace('\\','/')

                                tempfitsname=str(time.time()).replace('.','d') + '.fits'


                                # Save an image to the disk to use with source-extractor++
                                hdufocus = fits.PrimaryHDU()

                                # Cut the crusty edges
                                outputimg = outputimg[50:-50, 50:-50]
                                # (2) Mask hotspots quickly:
                                outputimg= mask_hot_pixels_fast(outputimg, sigma_thresh=9, sample_step=100)

                                hdufocus.header["NAXIS1"] = outputimg.shape[0]
                                hdufocus.header["NAXIS2"] = outputimg.shape[1]
                                hdufocus.data = outputimg.astype(np.float32)
                                hdufocus.writeto(tempdir + tempfitsname, overwrite=True, output_verify='silentfix')

                                if self.camera_known_gain < 1000:
                                    segain=self.camera_known_gain
                                else:
                                    segain=0

                                if self.pixscale == None:
                                    minarea=5
                                elif self.pixscale > 1.0:
                                    minarea=3
                                else:
                                    minarea= ((-9.2421 * self.pixscale) + 16.553)/ temp_focus_bin

                                command = (
                                    f"/home/obs/miniconda3/bin/sourcextractor++"
                                    f" --detection-image {tempdir_in_wsl}{tempfitsname}"
                                    f" --detection-image-gain {segain}"
                                    f" --detection-threshold 5"
                                    f" --thread-count {2*multiprocessing.cpu_count()}"
                                    f" --output-catalog-filename {tempdir_in_wsl}{tempfitsname.replace('.fits','cat.fits')}"
                                    f" --output-catalog-format FITS"
                                    f" --output-properties PixelCentroid,FluxRadius,AutoPhotometry,PeakValue,KronRadius,ShapeParameters"
                                    f" --flux-fraction 0.5"
                                    f" --detection-minimum-area {math.ceil(minarea)}"
                                    f" --grouping-algorithm MOFFAT"
                                    f" --tile-size 10000"
                                    f" --tile-memory-limit 16384"
                                )

                                # now call wsl bash -ic "<command>"
                                cmd = ["wsl", "bash", "-ic", command]

                                try:
                                    result = subprocess.run(
                                        cmd,
                                        capture_output=True,  # if you want stdout/stderr in result.stdout, result.stderr
                                        text=True,            # decode bytes to str
                                        timeout=300,          # kill if >300 s
                                        check=True            # raise if exit-code ≠ 0
                                    )
                                    print(result.stdout)
                                except subprocess.TimeoutExpired:
                                    print("✖ sourcextractor++ timed out")
                                except subprocess.CalledProcessError as e:
                                    print(f"⚠️ exited with code {e.returncode}")

                                print ("s++: " + str(time.time()-googtime))
                                try:
                                    googtime=time.time()
                                    catalog=Table.read(tempdir+ tempfitsname.replace('.fits','cat.fits'))

                                    original_catalog=copy.deepcopy(catalog)

                                    # Remove rows where FLUX_RADIUS is 0 or NaN
                                    mask = (~np.isnan(catalog['flux_radius'])) & (catalog['flux_radius'] != 0)# & (catalog['kron_radius'] > 0)

                                    catalog = catalog[mask]

                                    # remove unrealistic estimates that are too small
                                    if not self.pixscale == None:
                                        if self.pixscale < 1.0:
                                            mask = (catalog['flux_radius']) > (1.5 * (self.pixscale * temp_focus_bin))
                                            catalog = catalog[mask]
                                    # else:
                                    mask = (catalog['flux_radius']) > 1.0
                                    catalog =catalog[mask]

                                    # # remove unrealistic estimates that are too small
                                    mask = (catalog['area']) > minarea
                                    catalog =catalog[mask]

                                    # get rid of things that are clearly near the edge
                                    ymax, xmax = outputimg.shape

                                    mask = (catalog['flux_radius']) > 1.0
                                    catalog =catalog[mask]

                                    mask = (catalog['pixel_centroid_x']) > 100
                                    catalog =catalog[mask]
                                    mask = (catalog['pixel_centroid_x']) < (xmax-100)
                                    catalog =catalog[mask]
                                    mask = (catalog['pixel_centroid_y']) > 100
                                    catalog =catalog[mask]
                                    mask = (catalog['pixel_centroid_y']) < (ymax-100)
                                    catalog =catalog[mask]


                                    mask = (catalog['area']) > minarea
                                    catalog =catalog[mask]

                                    # Get rid of things that are clearly not particularly circular
                                    #min_ellipticity=min(catalog['ellipticity'])
                                    mask = (catalog['ellipticity']) < 0.4#(min_ellipticity + 0.5)
                                    catalog =catalog[mask]

                                    # Dump some data out to the plot function
                                    if len(catalog) > 0 :

                                        # Extract positions
                                        x = catalog['pixel_centroid_x']
                                        y = catalog['pixel_centroid_y']
                                        positions = np.vstack((x, y)).T

                                        # Build KDTree for fast nearest-neighbor search
                                        tree = cKDTree(positions)

                                        # Query for all neighbors within 30 pixels (including self)
                                        neighbors = tree.query_ball_point(positions, r=30)

                                        # Determine which sources are isolated (only self in the neighbor list)
                                        isolated_mask = np.array([len(n) == 1 for n in neighbors])

                                        # Filter table
                                        catalog = catalog[isolated_mask]

                                        filename = str(time.time())
                                        plotpickle=pickle.dumps(
                                            (outputimg, original_catalog, catalog, 9, 3.0, g_dev['cam'].camera_path + g_dev["day"] + "/calib/", filename)
                                        )

                                        subprocess.run(
                                            ["python", "subprocesses/focusplots_subprocess.py"],
                                            input=plotpickle,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE,
                                            text=False  # MUST be False for binary data
                                        )

                                        print ("aftersource: " + str(time.time()-googtime))


                                        googtime=time.time()
                                        catalog=calculate_donut_distance(outputimg, catalog, search_radius_factor=3.0)
                                        print ("donuts: " + str(time.time()-googtime))
                                        print ("before")
                                        print ("Median donut distance = " + str(np.nanmedian(catalog['total_donut_distance'])))
                                        print ("Median Flux Radius    = " + str(np.nanmedian(np.asarray(catalog['flux_radius']))))
                                        # print (np.nanstd(np.asarray(catalog['flux_radius'])))
                                        print ((np.asarray(catalog['total_donut_distance'])))
                                        print ((np.asarray(catalog['flux_radius'])))
                                        #breakpoint()
                                        data = np.asarray(catalog['total_donut_distance'])
                                        good = data[np.isfinite(data)]
                                        # now clip on only the “good” values
                                        total_mean_donut_distance = sigma_clip(good,
                                                            sigma_lower=2, sigma_upper=4,
                                                            maxiters=5)
                                        # if you want the clipped mean:
                                        # total_mean_donut_distance = clipped.mean()

                                        # total_mean_donut_distance=sigma_clip(np.asarray(catalog['total_donut_distance']),sigma_lower=2,sigma_upper=4, maxiters=5)
                                        total_mean_donut_distance=total_mean_donut_distance.data[~total_mean_donut_distance.mask]
                                        total_mean_flux_radius=sigma_clip(np.asarray(catalog['flux_radius']),sigma_lower=2,sigma_upper=4, maxiters=5)
                                        total_mean_flux_radius=total_mean_flux_radius.data[~total_mean_flux_radius.mask]
                                        print ("after")
                                        print ("Median donut distance = " + str(total_mean_donut_distance))
                                        print ("Median Flux Radius    = " + str(total_mean_flux_radius))

                                        print ((np.asarray(catalog['total_donut_distance'])))
                                        print ((np.asarray(catalog['flux_radius'])))

                                        # breakpoint()

                                        # if np.median(total_mean_donut_distance) > (np.median(total_mean_flux_radius) * 2) :
                                        #     fwhm_values=total_mean_donut_distance
                                        # else:
                                        fwhm_values=total_mean_flux_radius

                                        print (np.nanstd(fwhm_values))

                                        # The HFR and the fwhm are roughly twice
                                        fwhm_values=fwhm_values *2
                                    else:
                                        fwhm_values=[]

                                except:
                                    plog ("problem with the fits table... probably not enough detections")
                                    fwhm_values=[]

                                    print(traceback.format_exc())
                                    #breakpoint()

                                plog("No. of detections:  ", len(fwhm_values))

                                print (fwhm_values)

                                if len(fwhm_values) < 5:
                                    fwhm_dict = {}
                                    fwhm_dict['rfp'] = np.nan

                                    fwhm_dict['rfr'] = np.nan
                                    fwhm_dict['rfs'] = np.nan
                                    fwhm_dict['sky'] = 200 #str(imageMedian)
                                    fwhm_dict['sources'] = str(len(fwhm_values))

                                else:

                                    fwhm_dict = {}
                                    fwhm_dict['rfp'] = np.median(fwhm_values) * temp_focus_bin
                                    if self.pixscale == None:
                                        fwhm_dict['rfr'] = np.median(fwhm_values)  * temp_focus_bin
                                        fwhm_dict['rfs'] = np.median(fwhm_values)  * temp_focus_bin

                                    else:
                                        fwhm_dict['rfr'] = np.median(fwhm_values) * self.pixscale * temp_focus_bin
                                        fwhm_dict['rfs'] = np.median(fwhm_values) * self.pixscale  * temp_focus_bin
                                    fwhm_dict['sky'] = 200 #str(imageMedian)
                                    fwhm_dict['sources'] = str(len(fwhm_values))

                                if fwhm_dict['rfr'] < 1.0:
                                    plog ("Unreasonable RFR value, setting focus to nan")
                                    fwhm_dict['rfp'] = np.nan

                                    fwhm_dict['rfr'] = np.nan
                                    fwhm_dict['rfs'] = np.nan
                                    fwhm_dict['sky'] = 200 #str(imageMedian)
                                    fwhm_dict['sources'] = str(len(fwhm_values))

                                plog ("FWHM: " + str(fwhm_dict['rfr']))

                            except:
                                print ("couldn't do blob photometry: ")
                                print(traceback.format_exc())
                        else: #if not detected_donuts: # Do confirmation moffet photometry

                            try:

                                fx, fy = outputimg.shape

                                # Make a mask of NaNs
                                nan_mask = np.isnan(outputimg)

                                # Replace NaNs with 0 temporarily
                                filled = np.copy(outputimg)
                                filled[nan_mask] = 0

                                # Create a distance map to the nearest non-NaN
                                distance, indices = ndimage.distance_transform_edt(nan_mask, return_indices=True)

                                # Map the original non-NaN values into the NaN locations
                                filled[nan_mask] = outputimg[tuple(indices[:, nan_mask])]#

                                outputimg=filled

                                bkg = sep.Background(outputimg, bw=32, bh=32, fw=3, fh=3)
                                bkg.subfrom(outputimg)

                                # Estimate a noise level (even if background subtracted, the noise remains)
                                noise = mad_std(outputimg)

                                # Set a detection threshold (5 sigma above noise, for example)
                                daofind = DAOStarFinder(fwhm=3.0, threshold=5.*noise)

                                # Find sources
                                sources = daofind(outputimg)
                                # Size of the cutouts
                                if self.pixscale == None:
                                    stamp_size = max(10 * (1/0.1),25)  # pixels
                                else:
                                    stamp_size = max(10 * (1/self.pixscale),25)  # pixels

                                cutouts = []
                                positions = []

                                # Step 1: Sort by 'flux' in descending order
                                sources.sort('flux')
                                sources.reverse()  # Because astropy sorts ascending by default

                                # Step 2: Trim to top 50 rows (or all if fewer)
                                top_sources = sources[:50]

                                for source in top_sources:
                                    x, y = source['xcentroid'], source['ycentroid']
                                    try:
                                        cutout = Cutout2D(outputimg, (x, y), (stamp_size, stamp_size))
                                        cutouts.append(cutout.data)
                                        positions.append((x, y))
                                    except Exception:
                                        pass

                                fwhms = []

                                def multiprocess_fwhm(cutouts, positions, processes=4):
                                    with Pool(processes=processes) as pool:
                                        results = pool.map(fit_moffat_worker, zip(cutouts, positions))
                                    # Filter out failed fits
                                    return [r for r in results if r is not None]

                                # Get number of CPUs
                                num_cpus = multiprocessing.cpu_count()

                                fwhms = multiprocess_fwhm(cutouts, positions, processes=max(1, num_cpus - 1))

                                fwhms=np.array(fwhms)



                                fwhms=fwhms[~np.isnan(fwhms)]
                                fwhms = fwhms[fwhms >= 0.5]
                                plog ("N of sources processed: " + str(len(sources)))


                                rfp = bn.nanmedian(fwhms) * temp_focus_bin
                                if self.pixscale == None:
                                    rfr = None
                                    rfs = None

                                else:
                                    rfr = rfp * self.pixscale
                                    rfs = bn.nanstd(fwhms) * self.pixscale * temp_focus_bin
                                    if rfr < 1.0 or rfr  > 16:
                                        print (rfr)
                                        rfr= np.nan
                                        rfp= np.nan

                                fwhm_dict = {}
                                fwhm_dict['rfp'] = rfp
                                fwhm_dict['rfr'] = rfr
                                fwhm_dict['rfs'] = rfs

                                fwhm_dict['sky'] = 200 #str(imageMedian)
                                fwhm_dict['sources'] = str(len(sources))

                                plog ("FWHM: " + str(fwhm_dict['rfr']))

                                #breakpoint()


                            except:
                                print ("couldn't do gaussian photometry: ")
                                print(traceback.format_exc())
                    except:
                        print ("couldn't do focus photometry: ")
                        print(traceback.format_exc())



                    ########################################################################################

                    g_dev['obs'].fwhmresult['FWHM'] = float(fwhm_dict['rfr'])
                    g_dev['obs'].fwhmresult['No_of_sources'] = float(
                        fwhm_dict['sources'])
                    g_dev['obs'].fwhmresult["mean_focus"] = focus_position

                    g_dev['obs'].fwhmresult['error'] = False

                    expresult['FWHM'] = g_dev['obs'].fwhmresult['FWHM']
                    expresult["mean_focus"] = focus_position
                    expresult['No_of_sources'] = fwhm_dict['sources']


                    plog("Focus at " + str(focus_position) + " is " +
                         str(round(float(g_dev['obs'].fwhmresult['FWHM']), 2)))

                    plog ("Stored")

                    try:
                        hdusmallheader["SEPSKY"] = str(fwhm_dict['sky'])
                    except:
                        hdusmallheader["SEPSKY"] = -9999
                    try:
                        hdusmallheader["FWHM"] = (
                            float(fwhm_dict['rfp'], 2), 'FWHM in pixels')
                        hdusmallheader["FWHMpix"] = (
                            float(fwhm_dict['rfp'], 2), 'FWHM in pixels')
                    except:
                        hdusmallheader["FWHM"] = (-99, 'FWHM in pixels')
                        hdusmallheader["FWHMpix"] = (-99, 'FWHM in pixels')

                    try:
                        hdusmallheader["FWHMasec"] = (
                            float(fwhm_dict['rfr'], 2), 'FWHM in arcseconds')
                    except:
                        hdusmallheader["FWHMasec"] = (-99,
                                                      'FWHM in arcseconds')
                    try:
                        hdusmallheader["FWHMstd"] = (
                            float(fwhm_dict['rfs'], 2), 'FWHM standard deviation in arcseconds')
                    except:

                        hdusmallheader["FWHMstd"] = (-99,
                                                     'FWHM standard deviation in arcseconds')

                    try:
                        hdusmallheader["NSTARS"] = (
                            str(fwhm_dict['sources']), 'Number of star-like sources in image')
                    except:
                        hdusmallheader["NSTARS"] = (-99,
                                                    'Number of star-like sources in image')

                    if self.site_config['keep_focus_images_on_disk']:
                        g_dev['obs'].to_slow_process(1000, ('focus', cal_path + cal_name, outputimg, hdusmallheader,
                                                            frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))

                        if self.site_config["save_to_alt_path"] == "yes":
                            g_dev['obs'].to_slow_process(1000, ('raw_alt_path', self.alt_path + g_dev["day"] + "/calib/" + cal_name, outputimg, hdusmallheader,
                                                                frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec))


                    text = open(im_path + text_name, "w")
                    text.write(str(hdusmallheader))
                    text.close()

                    # Send focus image fits header txt to AWS
                    self.obs.enqueue_for_fastAWS( im_path, text_name, exposure_time)

                    return expresult

# FLAT ACQUISITION SECTION

                if frame_type[-4:] == "flat":
                    current_camera_temperature, cur_humidity, cur_pressure, cur_pwm = (
                        self._temperature())
                    image_saturation_level = self.settings["saturate"]
                    if self.settings['is_osc']:
                        temp_is_osc = True
                        osc_fits = copy.deepcopy(outputimg)

                        debayered = []
                        max_median = 0

                        debayered.append(osc_fits[::2, ::2])
                        debayered.append(osc_fits[::2, 1::2])
                        debayered.append(osc_fits[1::2, ::2])
                        debayered.append(osc_fits[1::2, 1::2])

                        # crop each of the images to the central region
                        oscounter = 0
                        for oscimage in debayered:
                            cropx = int((oscimage.shape[0] - 500)/2)
                            cropy = int((oscimage.shape[1] - 500) / 2)
                            oscimage = oscimage[cropx:-cropx, cropy:-cropy]
                            oscmedian = bn.nanmedian(oscimage)
                            if oscmedian > max_median:
                                max_median = copy.deepcopy(oscmedian)
                                brightest_bayer = copy.deepcopy(oscounter)
                            oscounter = oscounter+1

                        del osc_fits
                        del debayered

                        central_median = max_median

                    else:
                        temp_is_osc = False
                        osc_fits = copy.deepcopy(outputimg)
                        cropx = int((osc_fits.shape[0] - 500)/2)
                        cropy = int((osc_fits.shape[1] - 500) / 2)
                        osc_fits = osc_fits[cropx:-cropx, cropy:-cropy]
                        central_median = bn.nanmedian(osc_fits)
                        del osc_fits

                    if central_median >= 0.80 * image_saturation_level:
                        plog("Flat rejected, center is too bright:  ", central_median)
                        g_dev["obs"].send_to_user("Flat rejected, too bright.", p_level="INFO")
                        expresult = {}
                        expresult["error"] = True
                        expresult["patch"] = central_median
                        expresult["camera_gain"] = np.nan

                        # signals to flat routine image was rejected, prompt return
                        return copy.deepcopy(expresult)

                    elif (
                        central_median
                        <= 0.25 * image_saturation_level
                    ) and not temp_is_osc:
                        plog("Flat rejected, center is too dim:  ", central_median)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too dim.", p_level="INFO"
                        )
                        expresult = {}
                        expresult["error"] = True
                        expresult["patch"] = central_median
                        expresult["camera_gain"] = np.nan
                        # If it is too dim and we need to wait, make sure there
                        # is a sufficient wait period between exposures, otherwise
                        # hundreds are taking while waiting for the sky to brighten.
                        if exposure_time < 3:
                            time.sleep(2)

                        return copy.deepcopy(expresult)  # signals to flat routine image was rejected, prompt return
                    elif (
                        central_median
                        <= 0.5 * image_saturation_level
                    ) and temp_is_osc:
                        plog("Flat rejected, center is too dim:  ", central_median)
                        g_dev["obs"].send_to_user(
                            "Flat rejected, too dim.", p_level="INFO"
                        )
                        expresult = {}
                        expresult["error"] = True
                        expresult["patch"] = central_median
                        expresult["camera_gain"] = np.nan

                        # If it is too bright and we need to wait, make sure there
                        # is a sufficient wait period between exposures, otherwise
                        # hundreds are taking while waiting for the sky to dim.
                        if exposure_time < 3:
                            time.sleep(2)

                        return copy.deepcopy(expresult) # signals to flat routine image was rejected, prompt return

                    else:
                        expresult = {}
                        # Now estimate camera gain.
                        camera_gain_estimate_image = copy.deepcopy(outputimg)

                        try:
                            # Get the brightest bayer layer for gains
                            if self.settings['is_osc']:
                                if brightest_bayer == 0:
                                    camera_gain_estimate_image = camera_gain_estimate_image[::2, ::2]
                                elif brightest_bayer == 1:
                                    camera_gain_estimate_image = camera_gain_estimate_image[::2, 1::2]
                                elif brightest_bayer == 2:
                                    camera_gain_estimate_image = camera_gain_estimate_image[1::2, ::2]
                                elif brightest_bayer == 3:
                                    camera_gain_estimate_image = camera_gain_estimate_image[1::2, 1::2]

                            cropx = int(
                                (camera_gain_estimate_image.shape[0] - 500)/2)
                            cropy = int(
                                (camera_gain_estimate_image.shape[1] - 500) / 2)
                            camera_gain_estimate_image = camera_gain_estimate_image[
                                cropx:-cropx, cropy:-cropy]
                            camera_gain_estimate_image = sigma_clip(
                                camera_gain_estimate_image, masked=False, axis=None)

                            cge_median = bn.nanmedian(
                                camera_gain_estimate_image)
                            cge_stdev = np.nanstd(camera_gain_estimate_image)
                            cge_sqrt = pow(cge_median, 0.5)
                            #cge_gain = 1/pow(cge_sqrt/cge_stdev, 2)
                            cge_gain = pow(cge_sqrt/cge_stdev, 2)

                            # We should only check whether the gain is good IF we have a good gain.
                            commissioning_flats = False

                            # Check if we have MOST of the flats we need
                            if os.path.exists(g_dev['obs'].local_flat_folder + this_exposure_filter):
                                files_in_folder = glob.glob(
                                    g_dev['obs'].local_flat_folder + this_exposure_filter + '/' + '*.n*')
                                files_in_folder = [
                                    x for x in files_in_folder if "tempcali" not in x]
                                max_files = self.settings['number_of_flat_to_store']
                                n_files = len(files_in_folder)
                                if not ((n_files/max_files) > 0.8):
                                    commissioning_flats = True
                            else:
                                commissioning_flats = True

                            # If we don't have a good gain yet, we are commissioning
                            if g_dev['seq'].current_filter_last_camera_gain > 50:
                                commissioning_flats = True

                            # low values SHOULD be ok.
                            if commissioning_flats:
                                g_dev["obs"].send_to_user(
                                    'Good flat value:  ' + str(int(central_median)) + ' Good Gain: ' + str(round(cge_gain, 2)))
                                plog('Good flat value:  ' + str(central_median) +
                                     ' Not testing gain until flats in commissioned mode.')

                            elif cge_gain < (g_dev['seq'].current_filter_last_camera_gain + 5 * g_dev['seq'].current_filter_last_camera_gain_stdev):
                                g_dev["obs"].send_to_user(
                                    'Good flat value:  ' + str(int(central_median)) + ' Good Gain: ' + str(round(cge_gain, 2)))
                                plog('Good flat value:  ' + str(central_median) +
                                     ' Good Gain: ' + str(round(cge_gain, 2)))

                            elif (not self.settings['reject_new_flat_by_known_gain']):
                                g_dev["obs"].send_to_user('Good flat value:  ' + str(int(central_median)) + ' Bad Gain: ' + str(
                                    round(cge_gain, 2)) + ' Flat rejection by gain is off.')
                                plog('Good flat value:  ' + str(central_median) + ' Bad Gain: ' +
                                     str(round(cge_gain, 2)) + ' Flat rejection by gain is off.')

                            else:
                                g_dev["obs"].send_to_user('Good flat value:  ' + str(int(
                                    central_median)) + ' Bad Gain: ' + str(round(cge_gain, 2)) + ' Flat rejected.')
                                plog('Good flat value:  ' + str(central_median) +
                                     ' Bad Gain: ' + str(round(cge_gain, 2)) + ' Flat rejected.')
                                expresult = {}
                                expresult["error"] = True
                                expresult["patch"] = central_median
                                expresult["camera_gain"] = np.nan
                                # signals to flat routine image was rejected, prompt return
                                return copy.deepcopy(expresult)

                            expresult["camera_gain"] = cge_gain

                        except Exception as e:
                            plog("Could not estimate the camera gain from this flat.")
                            plog(e)
                            expresult["camera_gain"] = np.nan
                        del camera_gain_estimate_image
                        expresult["error"] = False
                        expresult["patch"] = central_median

                        hdu = fits.PrimaryHDU()

                        # Flip flat fits around to correct orientation
                        if self.settings["transpose_fits"]:
                            hdu = fits.PrimaryHDU(
                                outputimg.transpose().astype('float32'))
                        elif self.settings["flipx_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.fliplr(outputimg.astype('float32'))
                            )
                        elif self.settings["flipy_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.flipud(outputimg.astype('float32'))
                            )
                        elif self.settings["rotate90_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.rot90(outputimg.astype('float32'))
                            )
                        elif self.settings["rotate180_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.rot90(outputimg.astype('float32'), 2)
                            )
                        elif self.settings["rotate270_fits"]:
                            hdu = fits.PrimaryHDU(
                                np.rot90(outputimg.astype('float32'), 3)
                            )
                        else:
                            hdu = fits.PrimaryHDU(
                                outputimg.astype('float32')
                            )
                        del outputimg

                        try:

                            hdu.header['PIXSCALE'] = self.pixscale
                        except:
                            hdu.header['PIXSCALE'] = 'unknown'

                        hdu.header['EXPTIME'] = exposure_time

                        hdu.header['OBSTYPE'] = 'flat'
                        hdu.header['FILTER'] = this_exposure_filter

                        # If the files are local calibrations, save them out to the local calibration directory
                        if not manually_requested_calibration:
                            g_dev['obs'].to_slow_process(200000000, ('localcalibration', raw_name00, hdu.data,
                                                         hdu.header, frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec, current_camera_temperature))

                        # Similarly to the above. This saves the RAW file to disk
                        if self.site_config['save_raw_to_disk']:
                            os.makedirs(
                                self.camera_path + g_dev["day"], exist_ok=True, mode=0o777
                            )

                            os.makedirs(
                                raw_path, exist_ok=True, mode=0o777
                            )
                            thread = threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw', raw_path + raw_name00, hdu.data, hdu.header,
                                             frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec, 'no', 'deprecated')),))
                            thread.daemon = True
                            thread.start()



                        # For sites that have "save_to_alt_path" enabled, this routine
                        # Saves the raw and reduced fits files out to the provided directories
                        if self.site_config["save_to_alt_path"] == "yes":
                            thread = threading.Thread(target=write_raw_file_out, args=(copy.deepcopy(('raw_alt_path', self.alt_path + g_dev["day"] + "/raw/" + raw_name00, hdu.data, hdu.header,
                                                                                             frame_type, g_dev["mnt"].current_icrs_ra, g_dev["mnt"].current_icrs_dec, 'no', 'deprecated')),))
                            thread.daemon = True
                            thread.start()

                        del hdu
                        return copy.deepcopy(expresult)

                expresult["calc_sky"] = 0  # avg_ocn[7]
                expresult["temperature"] = 0  # avg_foc[2]
                expresult["gain"] = 0
                expresult["filter"] = this_exposure_filter
                expresult["error"] = False

                blockended = False
                # Check that the block isn't ending during normal observing time (don't check while biasing, flats etc.)
                # Only do this check if a block end was provided.
                if g_dev['seq'].blockend != None:

                    # Check that the exposure doesn't go over the end of a block
                    endOfExposure = datetime.now(tz=timezone.utc) + timedelta(seconds=exposure_time)
                    now_date_timeZ = endOfExposure.isoformat().split('.')[0] + 'Z'

                    blockended = now_date_timeZ >= g_dev['seq'].blockend

                    if blockended or ephem.Date(ephem.now() + (exposure_time * ephem.second)) >= \
                            g_dev['events']['End Morn Bias Dark']:
                        plog(
                            "Exposure overlays the end of a block or the end of observing. Skipping Exposure.")
                        plog("And Cancelling SmartStacks.")
                        Nsmartstack = 1
                        sskcounter = 2
                        self.currently_in_smartstack_loop = False

                # filename same as raw_filename00 in post_exposure process
                if not frame_type[-4:] == "flat" and not frame_type in ["bias", "dark"] and not a_dark_exposure and not focus_image and not frame_type == 'pointing':
                    try:
                        im_type = "EX"
                        expresult["real_time_filename"] = obs_id + "-" + self.alias + '_' + str(frame_type) + '_' + str(
                            this_exposure_filter) + "-" + g_dev["day"] + "-" + next_seq + "-" + im_type + "00.fits.fz"
                    except:
                        plog(traceback.format_exc())
                return copy.deepcopy(expresult)

            else:
                remaining = round(self.completion_time - time.time(), 1)

                # Need to have a time sleep to release the GIL to run the other threads
                if self.completion_time - time.time() > 0:
                    time.sleep(
                        min(0.5, abs(self.completion_time - time.time())))

                if remaining < -15:
                    if remaining > -16:
                        #plog ("Camera overtime: " + str(remaining))
                        pass

                    g_dev['obs'].request_scan_requests()

                    # Check there hasn't been a cancel sent through
                    if g_dev["obs"].stop_all_activity:
                        plog("stop_all_activity cancelling out of camera exposure")
                        Nsmartstack = 1
                        sskcounter = 2
                        expresult["error"] = True
                        expresult["stopped"] = True
                        g_dev["obs"].exposure_halted_indicator = False
                        self.currently_in_smartstack_loop = False
                        return expresult

                    if g_dev["obs"].exposure_halted_indicator:
                        expresult["error"] = True
                        expresult["stopped"] = True
                        g_dev["obs"].exposure_halted_indicator = False
                        plog("Exposure Halted Indicator On. Cancelling Exposure.")
                        return expresult