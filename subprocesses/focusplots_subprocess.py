
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.patches import Ellipse
from matplotlib.collections import PatchCollection

import numpy as np

from astropy.nddata import Cutout2D

import time

import pickle

import sys

# import os

# from PIL import Image

def plot_bright_star_cutouts(outputimg, catalog,filepath,filename, n=9, margin=1.2):
    """
    Plot a sqrt(n)x sqrt(n) grid of the n brightest sources from an SX++ catalog.

    Parameters
    ----------
    outputimg : 2D numpy.ndarray
        The image array.
    catalog : astropy.table.Table
        SX++ catalog with columns:
        'pixel_centroid_x', 'pixel_centroid_y',
        'peak_value_x', 'peak_value_y',
        'kron_radius', 'ellipse_a', 'ellipse_b', 'ellipse_theta',
        'auto_flux', 'auto_mag', 'elongation', 'ellipticity'.
    n : int, optional
        Number of brightest stars to plot (default=9).
    margin : float, optional
        Factor to pad around the Kron ellipse (default=1.2).
    """
    # # pick top-n brightest
    # idx    = np.argsort(catalog['auto_flux'])[-n:][::-1]
    # bright = catalog[idx]

    # pick the 9 lowest-ellipticity objects
    idx = np.argsort(catalog['ellipticity'])[:9]
    bright = catalog[idx]

    # grid size
    m = int(np.ceil(np.sqrt(n)))
    fig, axes = plt.subplots(m, m, figsize=(m*3, m*3))
    axes = axes.flatten()

    for ax, src in zip(axes, bright):
        # convert 1-based FITS → 0-based NumPy
        x0 = src['pixel_centroid_x'] - 1
        y0 = src['pixel_centroid_y'] - 1

        # ellipse semi‐axes (in pixels)
        a = src['ellipse_a'] * src['kron_radius']
        b = src['ellipse_b'] * src['kron_radius']
        # half‐size of cutout box (odd total size)
        r_pix = int(np.ceil(max(a, b) * margin))
        size  = (2*r_pix + 1, 2*r_pix + 1)

        # make the cutout
        cut = Cutout2D(outputimg,
                        position=(x0, y0),
                        size=size,
                        mode='partial',
                        fill_value=np.nan)

        ax.imshow(cut.data, origin='lower', cmap='gray')

        # draw the elliptical Kron aperture
        ell = Ellipse(xy=(r_pix, r_pix),
                      width=2*a,
                      height=2*b,
                      angle=np.degrees(src['ellipse_theta']),
                      edgecolor='red',
                      facecolor='none',
                      linewidth=1)
        ax.add_patch(ell)

        # mark the peak pixel
        xp = src['peak_value_x'] - 1
        yp = src['peak_value_y'] - 1
        dx = xp - x0
        dy = yp - y0
        ax.scatter(r_pix + dx,
                    r_pix + dy,
                    marker='+',
                    s=50,
                    c='yellow')

        # annotate flux & mag
        ax.set_title(f"flux={src['auto_flux']:.0f},  mag={src['auto_mag']:.2f}",
                      fontsize=8, color='white',
                      backgroundcolor='black')
        ax.axis('off')

    plt.tight_layout()
    plt.savefig(filepath+filename+'brightstarplots.png', dpi=300, bbox_inches='tight')
    plt.close()


def plot_sourcextractor_pp(outputimg,catalog,filepath,filename,
                            centroid_x='pixel_centroid_x', centroid_y='pixel_centroid_y',
                            flux_radius='flux_radius', kron_radius='kron_radius',
                            peak_x='peak_value_x', peak_y='peak_value_y', peak_value='peak_value'):
    """
    Overlay SourceXtractor++ detections on an Axes using PatchCollections for circles.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The Axes to draw on (should already have the image plotted).
    catalog : astropy.table.Table or pandas.DataFrame
        Table containing at least the centroid, peak, flux_radius, and kron_radius columns.
    centroid_x, centroid_y : str
        Column names for pixel centroids.
    flux_radius : str
        Column name for flux radius values.
    kron_radius : str
        Column name for Kron radius values.
    peak_x, peak_y : str
        Column names for peak positions.
    peak_value : str
        Column name for peak intensity (used to size markers).
    """
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(outputimg, origin='lower', cmap='gray')
    ax.set_xlabel('X pixel')
    ax.set_ylabel('Y pixel')
    ax.set_title('SourceXtractor++ detections')
    # 1) plot pixel centroids (hollow cyan circles)
    ax.scatter(catalog[centroid_x], catalog[centroid_y],
                s=50, facecolors='none', edgecolors='cyan', label='Centroids')

    # 2) plot peak positions (yellow stars sized by peak value)
    sizes = (catalog[peak_value] / catalog[peak_value].max()) * 100
    ax.scatter(catalog[peak_x], catalog[peak_y],
                s=sizes, c='yellow', marker='*', label='Peaks')

    # 3) build Circle patches for radii
    flux_circs = [Circle((x, y), r) for x, y, r in zip(
        catalog[centroid_x], catalog[centroid_y], catalog[flux_radius]
    )]
    kron_circs = [Circle((x, y), r) for x, y, r in zip(
        catalog[centroid_x], catalog[centroid_y], catalog[kron_radius]
    )]

    # 4) create PatchCollections
    flux_pc = PatchCollection(flux_circs,
                              facecolor='none', edgecolor='red', linestyle='--', linewidths=1)
    kron_pc = PatchCollection(kron_circs,
                              facecolor='none', edgecolor='green', linestyle='-', linewidths=1)

    # 5) add collections to Axes
    ax.add_collection(flux_pc)
    ax.add_collection(kron_pc)

    # legend
    ax.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig(filepath+filename+'sourceplots.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    
payload = pickle.load(sys.stdin.buffer)

(outputimg, beforecatalog, aftercatalog, n, margin, filepath, filename) = payload


plot_bright_star_cutouts(outputimg, aftercatalog,filepath,filename, n, margin)

plot_sourcextractor_pp(outputimg, beforecatalog,filepath,filename +'before')

plot_sourcextractor_pp(outputimg, aftercatalog,filepath,filename +'after')
