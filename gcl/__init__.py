"""
Google Case Law Parser
~~~~~~~~~~~~~~~~~~~~~

A Python package for parsing Google Case Law and Patent data.
"""

from .main import GCLParse
from .google_patents_scrape import GooglePatents
from .proxy import ProxyMixin

from .version import __version__

__all__ = ["__version__", "GCLParse", "GooglePatents", "ProxyMixin"]
