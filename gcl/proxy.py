"""
This module provides integration with BrightData proxy for retrieving case content.
"""

import os
import logging
import ssl
import urllib.request
import urllib.error
import yaml
from pathlib import Path
from typing import Optional, Tuple
from time import sleep
from random import randint


logger = logging.getLogger(__name__)


class BrightDataConfig:
    """Configuration for BrightData proxy."""

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        config_file: Optional[str] = None,
        data_dir: Optional[str] = None,
    ):
        """
        Initialize BrightData configuration.

        Args:
            proxy_url: BrightData proxy URL
            config_file: Path to YAML config file
            data_dir: Directory for storing data files
        """
        self.proxy_url = proxy_url or os.getenv("BRIGHTDATA_PROXY")
        self.data_dir = Path(data_dir) if data_dir else Path("data/cases")

        if config_file:
            self._load_config(config_file)

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        if not self.proxy_url:
            raise ValueError(
                "BrightData proxy URL must be provided either through proxy_url parameter, "
                "BRIGHTDATA_PROXY environment variable, or config file."
            )

    def _load_config(self, config_file: str) -> None:
        """Load configuration from YAML file."""
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        self.proxy_url = config.get("proxy_url") or self.proxy_url
        if "data_dir" in config:
            self.data_dir = Path(config["data_dir"])

    @property
    def progress_file(self) -> Path:
        """Path to the scraping progress file."""
        return self.data_dir / "scraping_progress.json"


class BrightDataMixin:
    """Mixin class that adds BrightData proxy functionality to GCLParse."""

    def __init__(self, **kwargs):
        """Initialize BrightData functionality."""
        # Initialize with default values
        self.proxy_url = None
        self.config = None
        self.use_proxy = False

        # Initialize config if proxy parameters are provided
        if kwargs.get("proxy_url") or kwargs.get("config_file"):
            self.config = BrightDataConfig(
                proxy_url=kwargs.get("proxy_url"),
                config_file=kwargs.get("config_file"),
                data_dir=kwargs.get("data_dir"),
            )
            self.proxy_url = self.config.proxy_url
            self.use_proxy = bool(self.proxy_url)

            # Create URL opener with proxy
            self.opener = urllib.request.build_opener(
                urllib.request.ProxyHandler(
                    {"https": self.proxy_url, "http": self.proxy_url}
                ),
                urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
            )
            # Add headers to mimic a real browser
            self.opener.addheaders = [
                (
                    "User-Agent",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                ),
                (
                    "Accept",
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                ),
                ("Accept-Language", "en-US,en;q=0.5"),
                ("Referer", "https://scholar.google.com/"),
            ]

        # Call parent class initialization
        super().__init__(**kwargs)

    def _get_with_proxy(self, url_or_id: str) -> Tuple[str, str]:
        """
        Get case content using BrightData proxy.

        Args:
            url_or_id: URL or case ID to fetch

        Returns:
            Tuple of (url, html_content)
        """
        if not self.proxy_url:
            raise ValueError("BrightData proxy URL not provided")

        # Format the URL if it's just a case ID
        url = url_or_id
        if url_or_id.isdigit():
            url = f"https://scholar.google.com/scholar_case?case={url_or_id}"
        elif not url_or_id.startswith(("http://", "https://")):
            url = f"https://scholar.google.com/{url_or_id}"

        try:
            # Add a random delay between 2-5 seconds
            sleep(randint(2, 5))
            response = self.opener.open(url)
            html_content = response.read().decode("utf-8", errors="replace")
            return url, html_content

        except urllib.error.HTTPError as e:
            error_details = f"{e.code} {e.reason}"
            logger.error(f"HTTP Error fetching URL {url} with proxy: {error_details}")
            if hasattr(e, "headers"):
                logger.debug("Error Response Headers: %s", dict(e.headers))
            raise

        except urllib.error.URLError as e:
            logger.error(f"Connection Error fetching URL {url} with proxy: {e.reason}")
            raise

        except Exception as e:
            logger.error(f"Error fetching URL {url} with proxy: {str(e)}")
            raise
