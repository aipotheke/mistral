"""hidrive_copy: copy files from an IONOS HiDrive folder to local disk."""
from .client import HiDriveClient, HiDriveError

__all__ = ["HiDriveClient", "HiDriveError"]
