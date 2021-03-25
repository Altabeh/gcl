"""
This module scrapes patent data from Google Patents.

The offered features include downloading, parsing and serializing
patent data such as title, abstract, claims, and description.
"""

import json
import re

from bs4 import BeautifulSoup as BS

from gcl.settings import root_dir
from gcl.utils import create_dir, deaccent, get, regex, validate_url


class GooglePatents:

    __gp_base_url__ = "https://patents.google.com/"
    __relevant_patterns__ = [(r"[\t\r\n]", " "), (r" +", " "), (r"^ +| +$", "")]
    _data = None

    def __init__(self, **kwargs):
        self.data_dir = create_dir(kwargs.get("data_dir", root_dir / "gcl" / "data"))
        self.suffix = kwargs.get("suffix", "v1")

    @property
    def data(self):
        if self._data is None:
            self._data = {
                "patent_number": None,
                "url": None,
                "title": None,
                "abstract": None,
                "claims": {},
                "description": {},
            }

        return self._data

    def _scrape_claims(self):
        claim_tags = self.patent.select(".claims > *")
        last_independent_num = 1
        extra_count = 0
        for tag in claim_tags:
            in_tag = tag.find(
                lambda tag: tag.name == "div" and tag.attrs.get("num", None)
            )
            if in_tag:
                num = in_tag.attrs["num"]
                if regex(num, [(r"\d$", "")], sub=False):
                    if "-" in num:
                        if not regex(num, [(r"\d+-\d+", "")], sub=False):
                            extra_count += 1  # Fixes wrong counting of claims.
                        num = int(regex(num, [(r"-.*$", "")])) + extra_count
                    else:
                        num = int(num) + extra_count
                    context = regex(
                        tag.get_text(),
                        [*self.__relevant_patterns__, (r"^\d+\. ", "")],
                    )
                    attach_data = {
                        "claim_number": num,
                        "context": context,
                        "dependent_on": None,
                    }
                    self.data["claims"][num] = attach_data
                    if "claim-dependent" not in tag.attrs["class"]:
                        last_independent_num = num

                    else:
                        if num > 1:
                            if fn := regex(
                                context,
                                [(r"\s+claims?(?:\s+)?(\d+)", "")],
                                sub=False,
                                flags=re.I,
                            ):
                                last_independent_num = int(fn[0])

                            self.data["claims"][num][
                                "dependent_on"
                            ] = last_independent_num
        return

    def _scrape_description(self):
        description_lines = self.patent.find_all(
            lambda tag: tag.name == "div"
            and tag.has_attr("class")
            and regex(
                tag.attrs.get("class"),
                [(r"description-(?:line|paragraph)", "")],
                sub=False,
            )
            and tag.has_attr("num")
        )
        for pl in description_lines:
            self.data["description"][
                regex(
                    pl.attrs["num"],
                    [(r"[(\[\])]", ""), (r"^[a-z0\-]+", "")],
                    flags=re.I,
                )
            ] = regex(pl.get_text(), self.__relevant_patterns__)
        return

    def _scrape_abstract(self):
        abstract_tags = self.patent.find_all("div", class_="abstract")
        abstract = " ".join(
            [regex(ab.get_text(), self.__relevant_patterns__) for ab in abstract_tags]
        )
        self.data["abstract"] = abstract
        return

    def _scrape_title(self):
        self.data["title"] = regex(
            self.patent.find("h1", attrs={"itemprop": "pageTitle"}).get_text(),
            [*self.__relevant_patterns__, (r" - Google Patents|^.*? - ", "")],
        )
        return

    def patent_data(
        self,
        number_or_url: str,
        skip_patent=False,
        include_description=False,
        save_unless_empty=[
            "title",
        ],
        return_data=[],
        **kwargs,
    ):
        """
        Download and scrape data for a patent with Patent (Application) No. or valid url `number_or_url`.

        Example
        -------
        >>> patent_data('https://patents.google.com/patent/US20150278825A1/en')

        Args
        ----
        :param skip_patent: ---> bool: if true, skips downloading patent and rather looks for
                                       a local patent file under `patents` folder.
        :param include_description: ---> bool: if true, the description will be included in the serialized data.
        :param save_unless_empty: ---> list: contains a list of parameters that if have no value in the patent,
                                       will abort saving. Possible values: "claims", "description", "abstract",
                                       "tilte".
        :param return_data: ---> list: contains the parameters whose data will be returned upon serialization.
        :param kwargs: ---> dict: contains arbitrary key, value pairs to be added to the serialized data.
        """
        # List of parameters that would abort saving if scraping them fails to return nonempty values.
        abort = []

        # Assume that the patent is not found
        found = False

        [patent_number, url] = [""] * 2

        subfolder = patent_number
        for k, v in kwargs.items():
            if k == "subfolder":
                subfolder = v
            else:
                self.data[k] = v

        try:
            if validate_url(number_or_url):
                url = number_or_url
                if fn := regex(url, [(r"(?<=patent/).*?(?=/|$)", "")], sub=False):
                    patent_number = fn[0]
        except:
            patent_number = number_or_url

        json_path = (
            self.data_dir
            / "patent"
            / f"patent_{self.suffix}"
            / subfolder
            / f"{patent_number}.json"
        )

        if json_path.is_file():
            if return_data:
                with open(json_path.__str__(), "r") as f:
                    self._data = json.load(f)
            found = True

        else:
            if not skip_patent:
                url = f"{self.__gp_base_url__}patent/{patent_number}"
                status, html = get(url)
                if status == 200:
                    found = True
                    self.patent = BS(deaccent(html), "html.parser")
                    self._scrape_claims()

                    if include_description:
                        self._scrape_description()

                    self._scrape_abstract()
                    self._scrape_title()
                    self.data["url"] = url
                    self.data["patent_number"] = patent_number

                    abort = [par for par in save_unless_empty if not self.data[par]]
                    if not abort:
                        create_dir(json_path.parent)
                        with open(json_path.__str__(), "w") as f:
                            print(
                                f"Saving patent data for Patent No. {patent_number}..."
                            )
                            json.dump(self.data, f, indent=4)

        if return_data:
            if not found:
                return found, None

            for a in abort:
                if a == "title":
                    if patent_number:
                        if skip_patent:
                            print(
                                f"Patent No. {patent_number} has not been downloaded yet. Please set `skip_patent=False`"
                            )
                        else:
                            print(
                                f"Invalid patent number detected; saving Patent No. {patent_number} was stopped"
                            )
                else:
                    print(
                        f"The patent {a} came back empty; saving Patent No. {patent_number} was stopped"
                    )

                return found, None

            return found, *(self.data[d] for d in return_data)
        
        self._data = None
        return
