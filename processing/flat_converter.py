import numpy
import astropy
from astropy.io import fits
from astropy.convolution import Gaussian2DKernel, convolve, interpolate_replace_nans

hdu = fits.open('FLAT_air_master_bin1.fits')


kernel = Gaussian2DKernel(x_stddev=3,y_stddev=3)



flatImage=numpy.asarray(hdu[0].data, dtype=numpy.float32)
flatImage[flatImage < 0.1] = numpy.nan

flatImage=interpolate_replace_nans(flatImage, kernel)
flatImage[flatImage < 0.1] = 0.8
flatImage[numpy.isnan(flatImage)] = 0.8
numpy.save('masterFlat_air_bin1.npy', flatImage)
numpy.save('masterFlat_w_bin1.npy', flatImage)

breakpoint()