"""MKPFS package root.

MkPFS is a toolkit for building, verifying, browsing, and managing PlayStation PFS images.
"""

from .discovery import (
    ProgressEvent,
    cli_metadata,
    default_image_basename,
    default_output_name,
    get_cli_metadata,
    normalize_output_path,
    register_progress_handler,
)
from .pbar import Progress

__version__: str = "1.0.0"
