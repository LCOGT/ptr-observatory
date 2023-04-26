# -*- coding: utf-8 -*-
"""
Created on Sun Mar 12 02:34:55 2023

@author: observatory
"""

import numpy as np
gscale1 = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
gscale2 = '@%#*+=-:. '


def get_average_l(image):
    im = np.array(image)
    w, h = im.shape
    return np.average(im.reshape(w * h))


def np_array_to_ascii(pil_image, cols, scale, more_levels):
    global gscale1, gscale2
    W, H = pil_image.size[0], pil_image.size[1]
    print("input image dims: %d x %d" % (W, H))
    w = W / cols
    h = w / scale
    rows = int(H / h)

    print("cols: %d, rows: %d" % (cols, rows))
    print("tile dims: %d x %d" % (w, h))
    if cols > W or rows > H:
        print("Image too small for specified cols!")
        exit(0)

    aimg = []
    for j in range(rows):
        y1 = int(j * h)
        y2 = int((j + 1) * h)

        if j == rows - 1:
            y2 = H

        aimg.append("")

        for i in range(cols):
            x1 = int(i * w)
            x2 = int((i + 1) * w)

            if i == cols - 1:
                x2 = W

            img = pil_image.crop((x1, y1, x2, y2))
            avg = int(get_average_l(img))

            if more_levels:
                gsval = gscale1[int((avg * 69) / 255)]
            else:
                gsval = gscale2[int((avg * 9) / 255)]

            aimg[j] += gsval

    return aimg
