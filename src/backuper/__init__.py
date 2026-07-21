"""backuper - modular incremental backup tool."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("backuper")
except PackageNotFoundError:
    __version__ = "0+unknown"
