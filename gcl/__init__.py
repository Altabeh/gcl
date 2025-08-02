"""
Google Case Law Parser
~~~~~~~~~~~~~~~~~~~~~

A Python package for parsing Google Case Law and Patent data.
"""

from .main import GCLParse
from .google_patents_scrape import GooglePatents
from .search_api import SearchAPIMixin, SearchAPIConfig

__version__ = "1.3.1"

__all__ = ["GCLParse", "GooglePatents", "SearchAPIMixin", "SearchAPIConfig"]
