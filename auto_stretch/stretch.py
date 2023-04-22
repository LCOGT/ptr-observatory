from astropy.io import fits
import numpy as np
import time
"""
This product is based on software from the PixInsight project, developed by
Pleiades Astrophoto and its contributors (http://pixinsight.com/).
"""

class Stretch:

    def __init__(self, target_bkg=0.25, shadows_clip=-1.25):
        self.shadows_clip = shadows_clip
        self.target_bkg = target_bkg

    def _get_avg_dev(self, data, median):
        """Return the average deviation from the median.

        Args:
            data (np.array): array of floats, presumably the image data
        """
        #median = np.median(data)
        n = data.size
        #gutime=time.time()
        #median_deviation = lambda x: abs(x - median)
        #avg_dev = np.sum( median_deviation(data) / n )
        #avg_dev = np.mean( median_deviation(data))
        #avg_dev = np.mean(np.absolute(data-median))
        avg_dev = np.sum( np.absolute(data-median) / n )
        #print ("guttime: " + str(time.time() - gutime))
        
        return avg_dev


    def _mtf(self, m, x):
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
        #googtime=time.time()
        shape = x.shape
        #breakpoint()
        #x = x.flatten()
        x = x.ravel()
        
        zeros = x==0
        halfs = x==m
        ones = x==1
        others = np.logical_xor((x==x), (zeros + halfs + ones))

        x[zeros] = 0
        x[halfs] = 0.5
        x[ones] = 1
        x[others] = (m - 1) * x[others] / ((((2 * m) - 1) * x[others]) - m)
        #print ("time: " + str(time.time()-googtime))
        return x.reshape(shape)


    def _get_stretch_parameters(self, data):
        """ Get the stretch parameters automatically.
        m (float) is the midtones balance
        c0 (float) is the shadows clipping point
        c1 (float) is the highlights clipping point
        """
        
        median = np.median(data.ravel())
        
        avg_dev = self._get_avg_dev(data, median)
        

        c0 = np.clip(median + (self.shadows_clip * avg_dev), 0, 1)
        m = self._mtf(self.target_bkg, median - c0)


        return {
            "c0": c0,
            #"c1": 1,
            "m": m
        }


    def stretch(self, data):
        """ Stretch the image.

        Args:
            data (np.array): the original image data array.

        Returns:
            np.array: the stretched image data
        """
        #googtime=time.time()
        # Normalize the data
        try:
            data = data / np.max(data)
        except:
            data = data    #NB this avoids div by 0 is image is a very flat bias

        #data=data/np.max(data)

        # Obtain the stretch parameters
        stretch_params = self._get_stretch_parameters(data)
        m = stretch_params["m"]
        c0 = stretch_params["c0"]
        #c1 = stretch_params["c1"]

        # Selectors for pixels that lie below or above the shadows clipping point
        #below = data < c0
        #above = data >= c0

        # Clip everything below the shadows clipping point
        data[data < c0] = 0
        #googtime=time.time()
        # For the rest of the pixels: apply the midtones transfer function
        data[data >= c0] = self._mtf(m, (data[data >= c0] - c0)/(1 - c0))
        #print ("time: " + str(time.time()-googtime))
        return data

