"""
This module provides integration with BrightData proxy for retrieving case content.
"""

import requests
import os
import logging
import ssl
import uuid
import yaml
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple
from time import sleep
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from random import randint

logger = logging.getLogger(__name__)


class DataImpulseMixin:
    """
    Helper mixin to route traffic through the DataImpulse proxy.

    Usage:
    - Choose provider via kwarg `proxy_provider="dataimpulse"` when constructing the parser
    - Provide credentials via kwargs or environment variables
      - kwargs: `di_proxy_url`, `di_username`, `di_password`
      - env: `PROXY_URL`, `PROXY_USERNAME`, `PROXY_PASSWORD`

    If `proxy_provider` is not "dataimpulse", this mixin transparently
    defers to next mixin in MRO for proxy handling.
    """

    def __init__(self, **kwargs):
        # Preserve any prior attributes; only set if not already present
        self.proxy_provider = getattr(self, "proxy_provider", None)
        self.use_proxy = getattr(self, "use_proxy", False)

        provider = kwargs.get("proxy_provider", self.proxy_provider)
        self.proxy_provider = provider

        # Only initialize DataImpulse fields if explicitly chosen
        if provider == "dataimpulse":
            # Pull credentials from kwargs or environment
            self.di_proxy_url = kwargs.get("di_proxy_url") or os.environ.get(
                "PROXY_URL"
            )
            self.di_username = kwargs.get("di_username") or os.environ.get(
                "PROXY_USERNAME"
            )
            self.di_password = kwargs.get("di_password") or os.environ.get(
                "PROXY_PASSWORD"
            )

            # Use proxy only when we have a URL and credentials
            if self.di_proxy_url and self.di_username and self.di_password:
                self.use_proxy = True

        # Continue cooperative initialization
        super().__init__(**kwargs)

    @staticmethod
    def create_session(
        *,
        use_proxy: bool | None = None,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
        session_label: str | None = None,
        default_timeout: float | None = None,
    ) -> requests.Session:
        """
        Build a requests.Session configured for DataImpulse when credentials are provided.

        Args:
            use_proxy: Force using proxy (True) or not (False). If None, auto-detect by presence of proxy_url/ENV.
            proxy_url: Proxy gateway URL like "http://gw.dataimpulse.com:823".
            proxy_username: DataImpulse username.
            proxy_password: DataImpulse password.
            session_label: Optional short token to enforce a new sticky session with the provider.
            default_timeout: Optional default timeout to attach on the session via adapter.

        Returns:
            Configured requests.Session instance.
        """
        # Pull from environment if not provided

        env_proxy_url = os.environ.get("PROXY_URL")
        env_proxy_username = os.environ.get("PROXY_USERNAME")
        env_proxy_password = os.environ.get("PROXY_PASSWORD")

        proxy_url = proxy_url or env_proxy_url
        proxy_username = proxy_username or env_proxy_username
        proxy_password = proxy_password or env_proxy_password

        if use_proxy is None:
            use_proxy = bool(proxy_url and proxy_username and proxy_password)

        session = requests.Session()

        # Optional: attach default timeout via HTTPAdapter if requested
        if default_timeout is not None:
            try:

                class TimeoutHTTPAdapter(HTTPAdapter):
                    def __init__(self, *args, timeout: float | None = None, **kwargs):
                        self._timeout = timeout
                        super().__init__(*args, **kwargs)

                    def send(self, request, **kwargs):
                        if "timeout" not in kwargs or kwargs["timeout"] is None:
                            kwargs["timeout"] = self._timeout
                        return super().send(request, **kwargs)

                retry = Retry(
                    total=3,
                    backoff_factor=0.3,
                    status_forcelist=[429, 500, 502, 503, 504],
                )
                adapter = TimeoutHTTPAdapter(timeout=default_timeout, max_retries=retry)
                session.mount("http://", adapter)
                session.mount("https://", adapter)
            except Exception:
                # Fallback silently if adapter wiring fails
                pass

        if use_proxy:
            # Encode credentials directly in the proxy URL (requests' preferred way)
            # Example: http://user:pass@gw.dataimpulse.com:823
            try:
                from urllib.parse import urlparse, urlunparse

                parsed = urlparse(proxy_url)
                # Safeguard: ensure scheme and netloc exist
                if not parsed.scheme or not parsed.netloc:
                    return session

                auth_netloc = parsed.netloc
                # If credentials are not already embedded, embed them
                if "@" not in auth_netloc and proxy_username and proxy_password:
                    # Optionally append a session label for rotation, if not already present
                    final_username = proxy_username
                    if session_label and "session-" not in proxy_username:
                        final_username = f"{proxy_username}-session-{session_label}"
                    auth_netloc = f"{final_username}:{proxy_password}@{parsed.hostname}:{parsed.port}"

                clean_url = urlunparse(
                    (parsed.scheme, auth_netloc, parsed.path or "", "", "", "")
                )

                session.proxies = {
                    "http": clean_url,
                    "https": clean_url,
                }

            except Exception:
                # If anything goes wrong building proxy URL, return direct session
                return session

        return session

    def _get_with_proxy(self, url_or_id: str) -> Tuple[str, str]:
        """
        Fetch a URL using DataImpulse proxy when selected. If not selected,
        delegate to the next mixin's implementation.
        """
        # Decide provider dynamically if not set
        provider = getattr(self, "proxy_provider", None)
        if not provider:
            # Prefer DataImpulse if full credentials available
            di_url = getattr(self, "di_proxy_url", None) or os.environ.get("PROXY_URL")
            di_user = getattr(self, "di_username", None) or os.environ.get(
                "PROXY_USERNAME"
            )
            di_pass = getattr(self, "di_password", None) or os.environ.get(
                "PROXY_PASSWORD"
            )
            if di_url and di_user and di_pass:
                provider = self.proxy_provider = "dataimpulse"
                self.use_proxy = True
            elif getattr(self, "proxy_url", None):
                provider = self.proxy_provider = "brightdata"
                self.use_proxy = True

        # If provider is not DataImpulse, delegate to other mixins (e.g., BrightData)
        if provider != "dataimpulse":
            return super()._get_with_proxy(url_or_id)  # type: ignore[misc]

        # Build URL similar to main fetch logic
        url = url_or_id
        if url_or_id.isdigit():
            url = f"https://scholar.google.com/scholar_case?case={url_or_id}"
        elif not url_or_id.startswith(("http://", "https://")):
            url = f"https://scholar.google.com/{url_or_id}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://scholar.google.com/",
        }

        # Attempt with rotating session labels to trigger proxy rotation on provider side
        last_error: Exception | None = None
        for attempt in range(100):
            session = self.create_session(
                use_proxy=True,
                proxy_url=getattr(self, "di_proxy_url", None)
                or os.environ.get("PROXY_URL"),
                proxy_username=getattr(self, "di_username", None)
                or os.environ.get("PROXY_USERNAME"),
                proxy_password=getattr(self, "di_password", None)
                or os.environ.get("PROXY_PASSWORD"),
                session_label=uuid.uuid4().hex[:8],
                default_timeout=30,
            )
            try:
                resp = session.get(url, headers=headers)
                status = resp.status_code

                if status == 429:
                    logger.warning(
                        "Rate limited by DataImpulse upstream. Retrying after server hint..."
                    )
                    retry_after = resp.headers.get("Retry-After")
                    sleep(int(retry_after)) if retry_after else sleep(30)
                    continue

                if status == 200:
                    # Check for various Google redirects/challenges
                    if any(
                        x in resp.text
                        for x in [
                            "gs_captcha_f",
                            "accounts.google.com/v3/signin",
                            "accounts.google.com/ServiceLogin",
                            "google.com/sorry/index",
                            "Our systems have detected unusual traffic",
                        ]
                    ):
                        logger.warning(
                            "Google challenge/redirect detected on DataImpulse attempt %s. Rotating proxy...",
                            attempt + 1,
                        )
                        sleep(randint(2, 5))
                        continue

                    # Check if we got redirected to a Google domain
                    if (
                        "accounts.google.com" in resp.url
                        or "google.com/sorry" in resp.url
                    ):
                        logger.warning(
                            "URL redirected to Google auth/challenge page on attempt %s. Rotating proxy...",
                            attempt + 1,
                        )
                        sleep(randint(2, 5))
                        continue

                    return url, resp.text

                last_error = Exception(f"Server response via DataImpulse: {status}")
            except Exception as e:
                last_error = e
            finally:
                session.close()

        # Exceeded attempts
        if last_error:
            raise last_error
        raise Exception("Failed to fetch via DataImpulse after retries")

    @staticmethod
    def request(
        method: str,
        url: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        json_body: dict | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
        use_proxy: bool | None = None,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
    ) -> requests.Response:
        """Convenience method to perform a single HTTP request with optional proxy."""
        session = DataImpulseMixin.create_session(
            use_proxy=use_proxy,
            proxy_url=proxy_url,
            proxy_username=proxy_username,
            proxy_password=proxy_password,
        )
        try:
            resp = session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json_body,
                headers=headers,
                timeout=timeout,
            )
            return resp
        finally:
            # Close to avoid sticky sessions
            session.close()


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
        # Initialize with default values but preserve any previous mixin state
        self.proxy_url = getattr(self, "proxy_url", None)
        self.config = getattr(self, "config", None)
        # Only default to False if not already set by a previous mixin
        self.use_proxy = getattr(self, "use_proxy", False)

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
            response = self.opener.open(url)
            html_content = response.read().decode("utf-8", errors="replace")
            # Check for various Google redirects/challenges
            if any(
                x in html_content
                for x in [
                    "gs_captcha_f",
                    "accounts.google.com/v3/signin",
                    "accounts.google.com/ServiceLogin",
                    "google.com/sorry/index",
                    "Our systems have detected unusual traffic",
                ]
            ):
                logger.warning(
                    "Google challenge/redirect detected on BrightData. Consider rotating proxy and retrying."
                )
                raise urllib.error.URLError("Google challenge/redirect encountered")
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


class ProxyMixin(DataImpulseMixin, BrightDataMixin):
    """
    Unified proxy mixin that transparently selects between DataImpulse and BrightData.

    Selection order:
    1) If `proxy_provider` provided, use that provider
    2) Else if DataImpulse creds available (kwargs/env), use DataImpulse
    3) Else if BrightData config provided, use BrightData
    4) Else, no proxy
    """

    def __init__(self, **kwargs):
        # Detect explicit provider
        provider = kwargs.get("proxy_provider")

        # Probe DataImpulse creds
        di_url = kwargs.get("di_proxy_url") or os.environ.get("PROXY_URL")
        di_user = kwargs.get("di_username") or os.environ.get("PROXY_USERNAME")
        di_pass = kwargs.get("di_password") or os.environ.get("PROXY_PASSWORD")

        # Probe BrightData
        bd_url = kwargs.get("proxy_url") or os.environ.get("BRIGHTDATA_PROXY")
        bd_cfg = kwargs.get("config_file")

        if not provider:
            if di_url and di_user and di_pass:
                provider = "dataimpulse"
            elif bd_url or bd_cfg:
                provider = "brightdata"

        # Stash provider so child mixins can see it
        kwargs["proxy_provider"] = provider

        # Initialize both parents cooperatively; DataImpulseMixin first per MRO
        super().__init__(**kwargs)

    def _get_with_proxy(self, url_or_id: str) -> Tuple[str, str]:
        provider = getattr(self, "proxy_provider", None)
        if provider == "dataimpulse":
            # Call DataImpulseMixin implementation directly
            return DataImpulseMixin._get_with_proxy(self, url_or_id)
        if provider == "brightdata":
            # Call BrightDataMixin implementation directly
            return BrightDataMixin._get_with_proxy(self, url_or_id)
        # No provider selected; raise to let caller fallback to direct fetch
        raise ValueError("Proxy provider not configured")
