"""
This module scrapes patent data from Google Patents.

The offered features include downloading, parsing and serializing
patent data such as title, abstract, claims, and description.
"""

__version__ = "1.3.1"  # Directly specify version

import json
import re
from functools import wraps
from logging import getLogger
from threading import Thread, local
from bs4 import BeautifulSoup as BS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .settings import root_dir
from .utils import create_dir, deaccent, regex, validate_url

logger = getLogger(__name__)

__all__ = ["GooglePatents"]


def get(url):
    """Get page content using Selenium."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    for attempt in range(3):  # Try 3 times
        try:
            driver = webdriver.Remote(
                command_executor="http://localhost:4444/wd/hub", options=options
            )
            driver.set_page_load_timeout(30)
            driver.get(url)

            # Wait for body to be present
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            content = driver.page_source
            driver.quit()
            return 200, content

        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
            try:
                if "driver" in locals():
                    driver.quit()
            except Exception as e:
                logger.error(f"Error quitting driver: {str(e)}")
                pass
            if attempt == 2:  # Last attempt
                return 404, ""

            # Wait before retrying
            from time import sleep

            sleep(2)


class GooglePatents(Thread):
    __gp_base_url__ = "https://patents.google.com/"
    __relevant_patterns__ = [
        (r"\s", " "),
        (r"(?:\.Iaddend\.|\.Iadd\.)+", " "),
        (r" +", " "),
        (r"^ +| +$", ""),
    ]
    __claim_numbers_patterns__ = [(r"^(?:\s+)?(\d+)\.(?:\s+)?", "")]
    __dependent_claim_patterns__ = [
        (
            r"\s+claims?(?:\s+)?(\d+)(?:(?:\s+)?(or|\-|to|through|and)?(?:[claim\s]+)?(\d+))?|\s+(former|prior|above|foregoing|previous|precee?ding)(?:\s+)?claim(s)?",
            "",
        )
    ]
    __description_patterns__ = [(r"description\W+(?:line|paragraph)", "")]

    tl = local()

    def __init__(self, **kwargs):
        self.data_dir = create_dir(kwargs.get("data_dir", root_dir / "gcl" / "data"))
        self.suffix = kwargs.get("suffix", f"v{__version__}")

    def _data(self):
        self.tl.pat_data = {
            "patent_number": None,
            "url": None,
            "title": None,
            "abstract": None,
            "claims": {},
            "description": {},
        }
        return

    def _clear_thread(func):
        """
        Decorator for clearing all the locally assigned attributes of an instance of threading.local().
        """

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            self.tl.__dict__.clear()
            return result

        return wrapper

    def _scrape_claims(self):
        list_index = False
        claim_container = self.tl.patent.select_one(".claims")

        if claim_container:
            if claim_container.name in ["ol", "ul"]:
                list_index = True

            claim_tags = claim_container.find_all(
                lambda tag: tag.name in ["div", "li", "claim"], recursive=False
            )

            for i, tag in enumerate(claim_tags):
                context = tag.get_text()
                cited_claims = None

                if list_index:
                    num = i + 1
                else:
                    try:
                        num = int(
                            regex(
                                tag.get_text(),
                                self.__claim_numbers_patterns__,
                                sub=False,
                            )[0]
                        )
                    except IndexError:
                        # Sometimes claim numbering is messed up: Example: .Iaddend..Iadd.7
                        if fn := tag.find(
                            lambda tag: tag.name in ["claim", "div"],
                            "claim" in tag.attrs.get("class", []),
                        ):
                            if gn := fn.attrs.get("num"):
                                # In case a range of claims appear to be cancelled, this block picks up
                                # the last number and assigns it to `num`.
                                if gn_range := regex(
                                    gn, [(r"\d+[-\s]+(\d+)", "")], flags=re.I, sub=False
                                ):
                                    num = int(gn_range[0])

                                else:
                                    num = int(
                                        regex(
                                            gn,
                                            [(r"[\[()\]]", ""), (r"^[a-z0\-]", "")],
                                            flags=re.I,
                                        )
                                    )
                            else:
                                num = i + 1
                        else:
                            num = i + 1

                context = regex(
                    context,
                    [*self.__relevant_patterns__, *self.__claim_numbers_patterns__],
                )
                attach_data = {
                    "claim_number": num,
                    "context": context,
                    "dependent_on": None,
                }

                self.tl.pat_data["claims"][num] = attach_data
                if num > 1:
                    if fn := regex(
                        context,
                        self.__dependent_claim_patterns__,
                        sub=False,
                        flags=re.I,
                    ):
                        # Pick the first occurrence of cited claims.
                        gn = fn[0]

                        if gn[0]:
                            if gn[1]:
                                # A-C or Claim A to C --> dependent_on: [A, B, C].
                                if gn[2] and regex(
                                    gn[1], [(r"to|through|\-", "")], sub=False
                                ):
                                    cited_claims = [
                                        i for i in range(int(gn[0]), int(gn[2]) + 1)
                                    ]
                                # Claim A or/and Claim C --> dependent_on: [A, C].
                                elif gn[2] and regex(
                                    gn[1], [(r"or|and", "")], sub=False
                                ):
                                    cited_claims = [int(gn[0]), int(gn[2])]

                            else:
                                # Claim A --> dependent_on: [A].
                                cited_claims = [int(gn[0])]

                        else:
                            # ... any one of the former claims --> dependent_on: [A, B, C, ..., previous claim].
                            if gn[3] and gn[4]:
                                cited_claims = [i + 1 for i in range(num - 1)]

                            # ... the former claim --> dependent_on: [previous claim].
                            elif gn[3] and not gn[4]:
                                cited_claims = [num - 1]

                    self.tl.pat_data["claims"][num]["dependent_on"] = cited_claims
        return

    def _scrape_description(self) -> None:
        description_lines = self.tl.patent.find_all(
            lambda tag: tag.name == "div"
            and tag.has_attr("class")
            and regex(
                tag.attrs.get("class"),
                self.__description_patterns__,
                sub=False,
            )[0]
        )
        for i, pl in enumerate(description_lines):
            self.tl.pat_data["description"][i + 1] = regex(
                pl.get_text(), self.__relevant_patterns__
            )
        return

    def _scrape_abstract(self) -> None:
        abstract_tags = self.tl.patent.find_all("div", class_="abstract")
        abstract = " ".join(
            [regex(ab.get_text(), self.__relevant_patterns__) for ab in abstract_tags]
        )
        if abstract:
            self.tl.pat_data["abstract"] = abstract
        return

    def _scrape_title(self) -> None:
        self.tl.pat_data["title"] = regex(
            self.tl.patent.find("h1", id="title").get_text(),
            [*self.__relevant_patterns__, (r" - Google Patents|^.*? - ", "")],
        )
        return

    @_clear_thread
    def patent_data(
        self,
        number_or_url: str,
        language: str = "en",
        skip_patent: bool = False,
        include_description: bool = False,
        save_unless_empty: list = None,
        return_data: list = None,
        **kwargs,
    ) -> tuple or None:
        """
        Download and scrape data for a patent with Patent (Application) No. or valid url `number_or_url`.

        Example
        -------
        >>> patent_data('https://patents.google.com/patent/US20150278825A1/en')

        Args
        ----
        * :param language: ---> str: determines the language of the patent to be downloaded.
        * :param skip_patent: ---> bool: if true, skips downloading patent and rather looks for
        a local patent file under `patents` folder.
        * :param include_description: ---> bool: if true, the description will be included in the serialized data.
        * :param save_unless_empty: ---> list: contains a list of parameters that if have no value in the patent,
        will abort saving. Possible values: "claims", "description", "abstract", "tilte".
        * :param return_data: ---> list: contains the parameters whose data will be returned upon serialization.
        * :param kwargs: ---> dict: contains arbitrary key, value pairs to be added to the serialized data.
        """

        # Create thread-specific data attribute to store data.
        self._data()

        if not save_unless_empty:
            save_unless_empty = [
                "title",
            ]

        if not return_data:
            return_data = []

        # List of parameters that would abort saving if scraping them fails to return nonempty values.
        abort = []

        # Assume that the patent is not found
        found = False

        [patent_number, url] = [""] * 2

        subfolder = filename = patent_number
        for k, v in kwargs.items():
            if k == "subfolder":
                subfolder = v
            elif k == "filename":
                filename = v
            else:
                self.tl.pat_data[k] = v

        try:
            # Add base URL if just a patent number is provided
            if not number_or_url.startswith(("http://", "https://")):
                url = f"{self.__gp_base_url__}patent/{number_or_url.upper()}/en"
                patent_number = number_or_url.upper()
            else:
                url = validate_url(number_or_url)
                if fn := regex(url, [(r"(?<=patent/).*?(?=/|$)", "")], sub=False):
                    patent_number = fn[0].upper()
        except Exception as e:
            logger.error(f"Error validating URL: {e}")
            patent_number = number_or_url.upper()

        json_path = (
            self.data_dir
            / "patent"
            / f"patent_{self.suffix}"
            / f"{patent_number if not subfolder else subfolder}"
            / f"{patent_number if not filename else filename}.json"
        )

        if json_path.is_file():
            if return_data:
                with open(json_path.__str__(), "r") as f:
                    self.tl.pat_data = json.load(f)
            found = True

        else:
            if not skip_patent:
                url = f"{self.__gp_base_url__}patent/{patent_number}/{language}"
                status, html = get(url)

                if status == 200:
                    found = True
                    self.tl.patent = BS(deaccent(html), "html.parser")
                    self._scrape_claims()

                    if include_description:
                        self._scrape_description()

                    self._scrape_abstract()
                    self._scrape_title()
                    self.tl.pat_data["url"] = url
                    self.tl.pat_data["patent_number"] = patent_number

                    abort = [
                        par for par in save_unless_empty if not self.tl.pat_data[par]
                    ]
                    if not abort:
                        create_dir(json_path.parent)
                        with open(json_path.__str__(), "w") as f:
                            logger.info(
                                f"Saving patent data for Patent No. {patent_number}..."
                            )
                            json.dump(self.tl.pat_data, f, indent=4)

        if return_data:
            if not found:
                return found, None

            for a in abort:
                if a == "title":
                    if patent_number:
                        if skip_patent:
                            logger.info(
                                f"Patent No. {patent_number} has not been downloaded yet. Please set `skip_patent=False`"
                            )
                        else:
                            logger.info(
                                f"Invalid patent number detected; saving Patent No. {patent_number} was stopped"
                            )
                else:
                    logger.info(
                        f"The patent {a} came back empty; saving Patent No. {patent_number} was stopped"
                    )

                return found, None

            return found, *(self.tl.pat_data[d] for d in return_data)

        return
