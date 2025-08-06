"""
Google Case Law Parser
~~~~~~~~~~~~~~~~~~~~~

A Python package for parsing Google Case Law and Patent data.
"""

from .main import GCLParse
from .google_patents_scrape import GooglePatents
from .proxy import BrightDataMixin, BrightDataConfig

__version__ = "1.3.1"

__all__ = ["GCLParse", "GooglePatents", "BrightDataMixin", "BrightDataConfig"]
