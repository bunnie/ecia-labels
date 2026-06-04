"""ECIA EIGP 114 product and logistic label generator."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ecia-label-generator")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0+local"
