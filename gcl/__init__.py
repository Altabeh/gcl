"""
Google Case Law Parser
~~~~~~~~~~~~~~~~~~~~~

A Python package for parsing Google Case Law and Patent data.
"""

from .main import GCLParse
from .google_patents_scrape import GooglePatents
from .proxy import ProxyMixin

__version__ = "1.3.2"

__all__ = ["GCLParse", "GooglePatents", "ProxyMixin"]
