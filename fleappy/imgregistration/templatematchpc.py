import cv2
from scipy.ndimage.interpolation import shift
from skimage.feature import register_translation
import numpy as np
import logging
from pathlib import Path


def register(avg_img, tiff_stack, maxmovement=10):
    """ Register time series tiff using OpenCV template matching.

    Uses opencv to template match template to tiff stack, and returns the transform_spec, translational shifts in (y,x),
    necessary to correct movements. A 5x5 smoothing kernel is applied to reduce high frequency noise. This version also
    does frame by frame phase correction for resonant scanning.

    Args:
        avg_img (numpy.ndarray (y,x)): Template image to register to
        tiff_stack (numpy.ndarray (z,y,x)): Tiff stack to register

    Returns:
        transform_spec (numpy.ndarray float (y,x): translation pixel shifts to register tiff_stack
    """

    background = np.zeros_like(tiff_stack)
    frameSizeX, frameSizeY = avg_img.shape
    transform_spec = np.zeros((tiff_stack.shape[0], 3))
    avg_img = cv2.UMat(avg_img.astype(np.float32))

    kernel = np.ones((5, 5), np.float32)/25
    avg_img = cv2.filter2D(avg_img, -1, kernel)
    pixel_previous = None
    for idx, frame in enumerate(tiff_stack):
        pixel_shiftA, _, _ = register_translation(frame[1::2, :], frame[0::2, :], upsample_factor=20)
        pixel_shiftB, _, _ = register_translation(frame[1:-1:2, :], frame[2::2, :], upsample_factor=20)
        pixel_shift = [0, np.mean([pixel_shiftA[1], pixel_shiftB[1]])]
        frame[0::2, :] = shift(frame[0::2, :], pixel_shift)

        background[idx, :, :] = np.zeros_like(avg_img, dtype='float32')
        trim_frame = cv2.UMat(cv2.convertScaleAbs(
            frame[maxmovement:frameSizeX-maxmovement, maxmovement:frameSizeY-maxmovement]).astype(np.float32))
        trim_frame = cv2.filter2D(trim_frame, -1, kernel)
        res = cv2.matchTemplate(trim_frame, avg_img, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        yshift = max_loc[0]-maxmovement
        xshift = max_loc[1]-maxmovement
        transform_spec[idx, :] = [xshift, yshift, pixel_shift[1]]

    return transform_spec


def transform(img_stack, transform_spec):
    """Applies (y,x) translation to a series of images

    Args:
        img_stack (numpy.ndarray):  Uncorrected tiff stack (z, y, x)
        transform_spec (numpy.ndarray): Shifts to be applied to tiff stack in format (frameNum, (y,x))

    Returns:
        numpy.ndarray: Motion corrected tiff stack (z, y, x)
    """

    z, w, h = img_stack.shape
    registered = np.zeros((z, w, h))
    for idx, frame in enumerate(img_stack):
        frame[1::2, :] = shift(frame[1::2, :], (0, transform_spec[idx, 2]))
        registered[idx, :, :] = shift(frame, transform_spec[idx, 0:2])
    registered[registered < 0] = 0
    return registered.astype(np.uint16)


def join(transform_list, transform_spec):
    """Appends the next set of transformations to a previous set.

    Args:
        transform_list (numpy.ndarray): Next set of frame by frame transformations.
        transform_spec (numpy.ndarray): Previous frame by frame transformations.

    Raises:
        ValueError: If the new transform_list isn't of a (n,2) numpy array.

    Returns:
        numpy.ndarray: Joined transformation specification.
    """

    if transform_list is None:
        logging.info('Transform_list is none!')
        return transform_spec
    elif isinstance(transform_list, np.ndarray) and transform_list.shape[1] == 3:
        logging.info('Joining tspe')
        return np.concatenate((transform_list, transform_spec), axis=0)
    else:
        raise ValueError('The transform list isn\'t a numpy array of dimensions (n,2)!')


def save(transform_list, target):
    """Write the list of transformations to a file.

    Args:
        transform_list (numpy.ndarray): List of transformations.
        target (Path): File to write transformations to.
    """
    if isinstance(target, Path):
        np.savetxt(target, np.squeeze(transform_list), delimiter=',', fmt='%.1f', header=__name__)
    else:
        raise TypeError('Please specifiy a Path')


def load():
    """Load frame by frame transformations from file.

    TODO:
        * Implement templatematchingpc file loading.

    Raises:
        NotImplementedError: File loading is not yet supported
    """
    raise NotImplementedError('Transformation loading is not yet implemented.')


def create_template(img_stack):
    """Creates a template from the image stack.

    Args:
        img_stack (numpy.ndarray): image stack (t, y, x)

    Returns:
        numpy.ndarray: Mean Image 
    """
    for idx, frame in enumerate(img_stack):
        pixel_shift, _, _ = register_translation(frame[0::2, :], frame[1::2, :], upsample_factor=20)
        img_stack[idx, 1::2, :] = shift(frame[1::2, :], (0, pixel_shift[1]))
    return np.mean(img_stack, axis=0, dtype=np.float)
