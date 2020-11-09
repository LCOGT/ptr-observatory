# Licensed under a 3-clause BSD style license - see LICENSE.rst

import operator

import numpy as np
import pytest
from numpy.testing import assert_equal

from ..subset_array import ReprojectedArraySubset


class TestReprojectedArraySubset:

    def setup_method(self, method):

        self.array1 = np.random.random((123, 87))
        self.array2 = np.random.random((123, 87))
        self.array3 = np.random.random((123, 87))

        self.footprint1 = (self.array1 > 0.5).astype(int)
        self.footprint2 = (self.array2 > 0.5).astype(int)
        self.footprint3 = (self.array3 > 0.5).astype(int)

        self.subset1 = ReprojectedArraySubset(self.array1[20:88, 34:40],
                                              self.footprint1[20:88, 34:40],
                                              34, 40, 20, 88)

        self.subset2 = ReprojectedArraySubset(self.array2[50:123, 37:42],
                                              self.footprint2[50:123, 37:42],
                                              37, 42, 50, 123)

        self.subset3 = ReprojectedArraySubset(self.array3[40:50, 11:19],
                                              self.footprint3[40:50, 11:19],
                                              11, 19, 40, 50)

    def test_repr(self):
        assert repr(self.subset1) == '<ReprojectedArraySubset at [20:88,34:40]>'

    def test_view_in_original_array(self):
        assert_equal(self.array1[self.subset1.view_in_original_array],
                     self.subset1.array)
        assert_equal(self.footprint1[self.subset1.view_in_original_array],
                     self.subset1.footprint)

    def test_shape(self):
        assert self.subset1.shape == (68, 6)

    def test_overlaps(self):
        assert self.subset1.overlaps(self.subset1)
        assert self.subset1.overlaps(self.subset2)
        assert not self.subset1.overlaps(self.subset3)
        assert self.subset2.overlaps(self.subset1)
        assert self.subset2.overlaps(self.subset2)
        assert not self.subset2.overlaps(self.subset3)
        assert not self.subset3.overlaps(self.subset1)
        assert not self.subset3.overlaps(self.subset2)
        assert self.subset3.overlaps(self.subset3)

    @pytest.mark.parametrize('op', [operator.add, operator.sub,
                                    operator.mul, operator.truediv])
    def test_arithmetic(self, op):
        subset = op(self.subset1, self.subset2)
        assert subset.imin == 37
        assert subset.imax == 40
        assert subset.jmin == 50
        assert subset.jmax == 88
        expected = op(self.array1[50:88, 37:40], self.array2[50:88, 37:40])
        assert_equal(subset.array, expected)

    def test_arithmetic_nooverlap(self):
        subset = self.subset1 - self.subset3
        assert subset.imin == 34
        assert subset.imax == 34
        assert subset.jmin == 40
        assert subset.jmax == 50
        assert subset.shape == (10, 0)
