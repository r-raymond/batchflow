""" Contains Imagenette and Imagewoof datasets """

import os
from os.path import dirname, basename
import tempfile
import logging
import urllib.request
import tarfile
from io import BytesIO

import PIL
import tqdm
import numpy as np
from sklearn.preprocessing import LabelEncoder

from . import ImagesOpenset
from .. import DatasetIndex


logger = logging.getLogger('SmallImagenet')


class Imagenette(ImagesOpenset):
    """ Base class for ImagenetLike datasets

    Notes
    -----
    - Datasets contain both grayscale and colored images.
      Argument `drop_grayscale` controls whether grayscale images should be dropped.

    """
    SOURCE_URL = 'https://s3.amazonaws.com/fast-ai-imageclas/imagenette.tgz'
    num_classes = 10

    def __init__(self, *args, drop_grayscale=True, bar=False, preloaded=None, train_test=True, **kwargs):
        self.bar = tqdm.tqdm(total=2) if  bar else None
        self.drop_grayscale = drop_grayscale
        super().__init__(*args, preloaded=preloaded, train_test=train_test, **kwargs)
        if self.bar:
            self.bar.close()

    def download(self, path=None):
        """ Load data from website and extract it into numpy arrays """

        def _image_class(filepath):
            """ Image's class is determined by the parent folder of the image """
            return basename(dirname(filepath))

        def _is_train(filepath):
            """ Whether image belongs to train or val parts can be determined by
            the level 2 parent folder of the image
            """
            return basename(dirname(dirname(filepath))) == 'train'

        def _extract(archive, member):
            data = archive.extractfile(member).read()
            return PIL.Image.open(BytesIO(data))

        def _is_file_rgb(archive, member):
            """ Check whether archive member is a file.
            In case `drop_grayscale` set to `True` it verifies that the member is the RGB mode image as well.
            """
            if not self.drop_grayscale:
                return member.isfile()

            return member.isfile() and _extract(archive, member).mode == 'RGB'

        def _gather_extracted(archive, files):
            images = np.array([_extract(archive, file) for file in files], dtype=object)
            labels = np.array([_image_class(file.name) for file in files])
            labels_encoded = LabelEncoder().fit_transform(labels)
            return images, labels_encoded

        if path is None:
            path = tempfile.gettempdir()
        filename = os.path.basename(self.SOURCE_URL)
        localname = os.path.join(path, filename)

        if not os.path.isfile(localname):
            logger.info("Downloading %s", filename)
            urllib.request.urlretrieve(self.SOURCE_URL, localname)
            logger.info("Downloaded %s", filename)
            if self.bar:
                self.bar.update(1)

        logger.info("Extracting...")
        with tarfile.open(localname, "r:gz") as archive:
            files_in_archive = archive.getmembers()

            train_files = [file for file in files_in_archive if _is_file_rgb(archive, file) and _is_train(file.name)]
            train_data = _gather_extracted(archive, train_files)

            test_files = [file for file in files_in_archive if _is_file_rgb(archive, file) and not _is_train(file.name)]
            test_data = _gather_extracted(archive, test_files)

        logger.info("Extracted")
        if self.bar:
            self.bar.update(1)

        self._train_index = DatasetIndex(np.arange(len(train_data[0])))
        self._test_index = DatasetIndex(np.arange(len(test_data[0])))
        return train_data, test_data


class Imagenette320(Imagenette):
    """ The '320px' version of Imagenette.
    The shortest size resized to that size with their aspect ratio maintained.
    """
    SOURCE_URL = 'https://s3.amazonaws.com/fast-ai-imageclas/imagenette-320.tgz'


class Imagenette160(Imagenette):
    """ The '160px' version of Imagenette.
    The shortest size resized to that size with their aspect ratio maintained.
    """
    SOURCE_URL = 'https://s3.amazonaws.com/fast-ai-imageclas/imagenette-160.tgz'


class ImageWoof(Imagenette):
    """ Imagewoof dataset. See the https://github.com/fastai/imagenette for details.
    """
    SOURCE_URL = 'https://s3.amazonaws.com/fast-ai-imageclas/imagewoof.tgz'


class ImageWoof320(Imagenette):
    """ The '320px' version of Imagewoof.
    The shortest size resized to that size with their aspect ratio maintained.
    """
    SOURCE_URL = 'https://s3.amazonaws.com/fast-ai-imageclas/imagewoof-320.tgz'


class ImageWoof160(Imagenette):
    """ The '160px' version of Imagewoof.
    The shortest size resized to that size with their aspect ratio maintained.
    """
    SOURCE_URL = 'https://s3.amazonaws.com/fast-ai-imageclas/imagewoof-160.tgz'
