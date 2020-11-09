# Licensed under a 3-clause BSD style license - see LICENSE.rst

"""
WCS-related utilities
"""

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
from numpy.lib.stride_tricks import as_strided

__all__ = ['efficient_pixel_to_pixel', 'has_celestial']


def unbroadcast(array):
    """
    Given an array, return a new array that is the smallest subset of the
    original array that can be re-broadcasted back to the original array.

    See https://stackoverflow.com/questions/40845769/un-broadcasting-numpy-arrays
    for more details.
    """

    if array.ndim == 0:
        return array

    new_shape = np.where(np.array(array.strides) == 0, 1, array.shape)
    return as_strided(array, shape=new_shape)


def unique_with_order_preserved(items):
    """
    Return a list of unique items in the list provided, preserving the order
    in which they are found.
    """
    new_items = []
    for item in items:
        if item not in new_items:
            new_items.append(item)
    return new_items


def pixel_to_world_correlation_matrix(wcs):
    """
    Return a correlation matrix between the pixel coordinates and the
    high level world coordinates, along with the list of high level world
    coordinate classes.

    The shape of the matrix is ``(n_world, n_pix)``, where ``n_world`` is the
    number of high level world coordinates.
    """

    # We basically want to collapse the world dimensions together that are
    # combined into the same high-level objects.

    # Get the following in advance as getting these properties can be expensive
    all_components = wcs.low_level_wcs.world_axis_object_components
    all_classes = wcs.low_level_wcs.world_axis_object_classes
    axis_correlation_matrix = wcs.low_level_wcs.axis_correlation_matrix

    components = unique_with_order_preserved([c[0] for c in all_components])

    matrix = np.zeros((len(components), wcs.pixel_n_dim), dtype=bool)

    for iworld in range(wcs.world_n_dim):
        iworld_unique = components.index(all_components[iworld][0])
        matrix[iworld_unique] |= axis_correlation_matrix[iworld]

    classes = [all_classes[component][0] for component in components]

    return matrix, classes


def pixel_to_pixel_correlation_matrix(wcs1, wcs2):
    """
    Correlation matrix between the input and output pixel coordinates for a
    pixel -> world -> pixel transformation specified by two WCS instances.

    The first WCS specified is the one used for the pixel -> world
    transformation and the second WCS specified is the one used for the world ->
    pixel transformation. The shape of the matrix is
    ``(n_pixel_out, n_pixel_in)``.
    """

    matrix1, classes1 = pixel_to_world_correlation_matrix(wcs1)
    matrix2, classes2 = pixel_to_world_correlation_matrix(wcs2)

    if len(classes1) != len(classes2):
        raise ValueError("The two WCS return a different number of world coordinates")

    # Check if classes match uniquely
    unique_match = True
    mapping = []
    for class1 in classes1:
        matches = classes2.count(class1)
        if matches == 0:
            raise ValueError("The world coordinate types of the two WCS don't match")
        elif matches > 1:
            unique_match = False
            break
        else:
            mapping.append(classes2.index(class1))

    if unique_match:

        # Classes are unique, so we need to re-order matrix2 along the world
        # axis using the mapping we found above.
        matrix2 = matrix2[mapping]

    elif classes1 != classes2:

        raise ValueError("World coordinate order doesn't match and automatic matching is ambiguous")

    matrix = np.matmul(matrix2.T, matrix1)

    return matrix


def split_matrix(matrix):
    """
    Given an axis correlation matrix from a WCS object, return information about
    the individual WCS that can be split out.

    The output is a list of tuples, where each tuple contains a list of
    pixel dimensions and a list of world dimensions that can be extracted to
    form a new WCS. For example, in the case of a spectral cube with the first
    two world coordinates being the celestial coordinates and the third
    coordinate being an uncorrelated spectral axis, the matrix would look like::

        array([[ True,  True, False],
               [ True,  True, False],
               [False, False,  True]])

    and this function will return ``[([0, 1], [0, 1]), ([2], [2])]``.
    """

    pixel_used = []

    split_info = []

    for ipix in range(matrix.shape[1]):
        if ipix in pixel_used:
            continue
        pixel_include = np.zeros(matrix.shape[1], dtype=bool)
        pixel_include[ipix] = True
        n_pix_prev, n_pix = 0, 1
        while n_pix > n_pix_prev:
            world_include = matrix[:, pixel_include].any(axis=1)
            pixel_include = matrix[world_include, :].any(axis=0)
            n_pix_prev, n_pix = n_pix, np.sum(pixel_include)
        pixel_indices = list(np.nonzero(pixel_include)[0])
        world_indices = list(np.nonzero(world_include)[0])
        pixel_used.extend(pixel_indices)
        split_info.append((pixel_indices, world_indices))

    return split_info


def efficient_pixel_to_pixel(wcs1, wcs2, *inputs):
    """
    Wrapper that performs a pixel -> world -> pixel transformation with two
    WCS instances, and un-broadcasting arrays whenever possible for efficiency.
    """

    # Shortcut for scalars
    if np.isscalar(inputs[0]):
        world_outputs = wcs1.pixel_to_world(*inputs)
        if not isinstance(world_outputs, (tuple, list)):
            world_outputs = (world_outputs,)
        return wcs2.world_to_pixel(*world_outputs)

    # Remember original shape
    original_shape = inputs[0].shape

    matrix = pixel_to_pixel_correlation_matrix(wcs1, wcs2)
    split_info = split_matrix(matrix)

    outputs = [None] * wcs2.pixel_n_dim

    for (pixel_in_indices, pixel_out_indices) in split_info:

        pixel_inputs = []
        for ipix in range(wcs1.pixel_n_dim):
            if ipix in pixel_in_indices:
                pixel_inputs.append(unbroadcast(inputs[ipix]))
            else:
                pixel_inputs.append(inputs[ipix].flat[0])

        pixel_inputs = np.broadcast_arrays(*pixel_inputs)

        world_outputs = wcs1.pixel_to_world(*pixel_inputs)
        if not isinstance(world_outputs, (tuple, list)):
            world_outputs = (world_outputs,)
        pixel_outputs = wcs2.world_to_pixel(*world_outputs)

        for ipix in range(wcs2.pixel_n_dim):
            if ipix in pixel_out_indices:
                outputs[ipix] = np.broadcast_to(pixel_outputs[ipix], original_shape)

    return outputs


def has_celestial(wcs):
    """
    Returns `True` if there are celestial coordinates in the WCS.
    """
    if isinstance(wcs, WCS):
        return wcs.has_celestial
    else:
        for world_axis_class in wcs.low_level_wcs.world_axis_object_classes.values():
            if issubclass(world_axis_class[0], SkyCoord):
                return True
        return False


def efficient_pixel_to_pixel_with_roundtrip(wcs1, wcs2, *inputs):

    outputs = efficient_pixel_to_pixel(wcs1, wcs2, *inputs)

    # Now convert back to check that coordinates round-trip, if not then set to NaN
    inputs_check = efficient_pixel_to_pixel(wcs2, wcs1, *outputs)
    reset = np.zeros(inputs_check[0].shape, dtype=bool)
    for ipix in range(len(inputs_check)):
        reset |= (np.abs(inputs_check[ipix] - inputs[ipix]) > 1)
    if np.any(reset):
        for ipix in range(len(inputs_check)):
            outputs[ipix] = outputs[ipix].copy()
            outputs[ipix][reset] = np.nan

    return outputs
