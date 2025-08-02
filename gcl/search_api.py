"""
This module provides integration with SearchAPI.io for retrieving case citations and content.
"""

import os
import logging
import requests
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from time import sleep
from random import randint


logger = logging.getLogger(__name__)


class SearchAPIConfig:
    """Configuration for SearchAPI.io client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        config_file: Optional[str] = None,
        data_dir: Optional[str] = None,
    ):
        """
        Initialize SearchAPI configuration.

        Args:
            api_key: SearchAPI.io API key
            config_file: Path to YAML config file
            data_dir: Directory for storing data files
        """
        self.api_key = api_key or os.getenv("SEARCHAPI_KEY")
        self.data_dir = Path(data_dir) if data_dir else Path("data/alice_cases")

        if config_file:
            self._load_config(config_file)

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        if not self.api_key:
            raise ValueError(
                "SearchAPI.io API key must be provided either through api_key parameter, "
                "SEARCHAPI_KEY environment variable, or config file."
            )

    def _load_config(self, config_file: str) -> None:
        """Load configuration from YAML file."""
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        self.api_key = config.get("api_key") or self.api_key
        if "data_dir" in config:
            self.data_dir = Path(config["data_dir"])

    @property
    def csv_file(self) -> Path:
        """Path to the main CSV output file."""
        return self.data_dir / "alice_cases.csv"

    @property
    def html_file(self) -> Path:
        """Path to the HTML cases CSV file."""
        return self.data_dir / "alice_cases_html.csv"

    @property
    def cleaned_file(self) -> Path:
        """Path to the cleaned cases CSV file."""
        return self.data_dir / "alice_cases_cleaned.csv"

    @property
    def progress_file(self) -> Path:
        """Path to the scraping progress file."""
        return self.data_dir / "scraping_progress.json"


class SearchAPIMixin:
    """Mixin class that adds SearchAPI.io functionality to GCLParse."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """Initialize SearchAPI functionality."""
        super().__init__(**kwargs)
        self.api_key = api_key
        self.base_url = "https://www.searchapi.io/api/v1/search"

        # Default headers for SearchAPI requests
        self.search_api_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get_with_search_api(self, url_or_id: str) -> Tuple[str, str]:
        """
        Get case content using SearchAPI.io.

        Args:
            url_or_id: URL or case ID to fetch

        Returns:
            Tuple of (url, html_content)
        """
        if not self.api_key:
            raise ValueError("SearchAPI key not provided")

        # Format the URL if it's just a case ID
        url = url_or_id
        if url_or_id.isdigit():
            url = f"https://scholar.google.com/scholar_case?case={url_or_id}"
        elif not url_or_id.startswith(("http://", "https://")):
            url = f"https://scholar.google.com/{url_or_id}"

        params = {
            "engine": "google_scholar",
            "url": url,
            "api_key": self.api_key,
        }

        try:
            # Add a random delay between 2-5 seconds
            sleep(randint(2, 5))
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()

            data = response.json()
            if not data.get("html"):
                raise ValueError("No HTML content returned from SearchAPI")

            return url, data["html"]

        except Exception as e:
            logger.error(f"Error fetching URL {url} with SearchAPI: {str(e)}")
            raise

    def search_citations(
        self,
        cites_id: str,
        page: int = 1,
        num: int = 20,
        year_low: Optional[int] = None,
        year_high: Optional[int] = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Search for papers citing a specific case.

        Args:
            cites_id: Google Scholar case ID to search citations for
            page: Page number (1-based)
            num: Results per page
            year_low: Start year for filtering
            year_high: End year for filtering
            **kwargs: Additional parameters for the API

        Returns:
            API response data or None on error
        """
        if not self.api_key:
            raise ValueError("SearchAPI key not provided")

        params = {
            "engine": "google_scholar",
            "cites": cites_id,
            "page": page,
            "num": num,
            "api_key": self.api_key,
            "hl": "en",
            "as_sdt": "4",  # Filter for all US courts
            "sciodt": "4",  # Sort by relevance within US courts
        }

        if year_low is not None:
            params["as_ylo"] = year_low
        if year_high is not None:
            params["as_yhi"] = year_high

        params.update(kwargs)

        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error searching citations: {e}")
            return None
