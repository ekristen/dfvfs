#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2013 The PyVFS Project Authors.
# Please see the AUTHORS file for details on individual authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""An implementation of a filesystem cache."""
import bz2
import gzip
import logging
import os
import tarfile
import zipfile

from plaso.lib import errors
from plaso.lib import event
from plaso.lib import registry
from plaso.lib import sleuthkit
from plaso.lib import timelib
from plaso.lib import vss
from plaso.proto import transmission_pb2

import pytsk3
import pyvshadow


class FilesystemContainer(object):
  """A container for the filesystem and image."""

  def __init__(self, fs, img, path, offset=0, volume=None, store_nr=-1):
    """Container for objects needed to cache a filesystem connection.

    Args:
      fs: A FS_Info object.
      img: An Img_Info object.
      path: The path to the image.
      offset: An offset to the image.
      volume: If this is a VSS, the volume object.
      store_nr: If this is a VSS, the store number.
    """
    self.fs = fs
    self.img = img
    self.path = path
    self.offset = offset
    self.volume = volume
    self.store_nr = store_nr


class FilesystemCache(object):
  """A class to open and store filesystem objects in cache."""

  def __init__(self):
    """Set up the filesystem cache."""
    self.cached_filesystems = {}

  def OpenTskImage(self, path, offset=0):
    """Open and store a regular TSK image in cache.

    Args:
      path: Full path to the image file.
      offset: Offset in bytes to the start of the volume.

    Returns:
      A FilesystemContainer object that stores a cache of the FS.

    Raises:
      errors.UnableToOpenFilesystem: If it is not able to open the filesystem.
    """
    try:
      img = pytsk3.Img_Info(path)
    except IOError as e:
      raise errors.UnableToOpenFilesystem(
          'Unable to open image file. [%s]' % e)

    try:
      fs = pytsk3.FS_Info(img, offset=offset)
    except IOError as e:
      raise errors.UnableToOpenFilesystem(
          'Unable to mount image, wrong offset? [%s]' % e)

    return FilesystemContainer(fs, img, path, offset)

  def OpenVssImage(self, path, store_nr, offset=0):
    """Open and store a VSS image in cache.

    Args:
      path: Full path to the image file.
      store_nr: Integer, indicating the VSS store number.
      offset: Offset in bytes to the start of the volume.

    Returns:
      A FilesystemContainer object that stores a cache of the FS.
    """
    volume = pyvshadow.volume()
    fh = vss.VShadowVolume(path, offset)
    volume.open_file_object(fh)
    store = volume.get_store(store_nr)
    img = vss.VShadowImgInfo(store)
    fs = pytsk3.FS_Info(img)

    return FilesystemContainer(fs, img, path, offset, volume, store_nr)

  def Open(self, path, offset=0, store_nr=-1):
    """Return a filesystem from the cache.

    Args:
      path: Full path to the image file.
      offset: Offset in bytes to the start of the volume.
      store_nr: If this is a VSS then the store nr.

    Returns:
      If the filesystem object is cached it will be returned,
      otherwise it will be opened and then returned.
    """
    fs_hash = u'%s:%d:%d' % (path, offset, store_nr)

    if fs_hash in self.cached_filesystems:
      return self.cached_filesystems[fs_hash]

    if store_nr >= 0:
      fs = self.OpenVssImage(path, store_nr, offset)
    else:
      fs = self.OpenTskImage(path, offset)

    self.cached_filesystems[fs_hash] = fs
    return fs