"""Panel package for the mkpfs GUI - hosts the base panel and operation panels."""

from .base import BasePanel
from .batch import BatchPanel
from .exfat_panel import ExfatPanel
from .inspect import InspectPanel
from .pack_file import PackFilePanel
from .pack_folder import PackFolderPanel
from .tree import TreePanel
from .unpack import UnpackPanel
from .verify import VerifyPanel

__all__ = [
    "BatchPanel",
    "ExfatPanel",
    "InspectPanel",
    "PackFilePanel",
    "PackFolderPanel",
    "TreePanel",
    "UnpackPanel",
    "VerifyPanel",
]
