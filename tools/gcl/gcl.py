"""
This module provides a parser for Google case law
pages available at https://scholar.google.com/.

The offered features include scraping, parsing, serializing
and tagging important data such as bluebook citations, judge names, courts,
decision dates, case numbers, patents in suit, cited claims, footnotes and etc.

It also provides a useful labeled text of the case file that can be utilized
in machine-learning applications.
"""

from __future__ import absolute_import

import json
import re
import sys
from csv import QUOTE_ALL, writer
from datetime import datetime
from functools import reduce
from operator import concat
from pathlib import Path
from random import randint
from time import sleep

import requests
from bs4 import BeautifulSoup as BS
from bs4 import NavigableString
from reporters_db import EDITIONS, REPORTERS
from tqdm import tqdm

from regexes import GCLRegex, GeneralRegex
from uspto_api import USPTOscrape

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, BASE_DIR.__str__())

from tools.utils import (closest_value, create_dir, deaccent,
                         hyphen_to_numbers, load_json, multi_run, nullify,
                         proxy_browser, recaptcha_process, regex, rm_repeated,
                         rm_tree, shorten_date, sort_int, switch_ip,
                         validate_url)

__author__ = {"github.com/": ["altabeh"]}
__all__ = ["GCLParse"]


class GCLParse(GCLRegex, GeneralRegex):
    """
    Parser for Google case law pages.
    """

    base_url = "https://scholar.google.com/"
    _prioritize_citations = None
    _case = None

    # ------ Labels ------
    paragraph_label = "$" * 4
    footnote_label = "@" * 4
    citation_label = "#" * 4
    blockquote_label_s, blockquote_label_e = "$qq$", "$/qq$"
    pre_label_s, pre_label_e = "$rr$", "$/rr$"

    def __init__(self, **kwargs):
        self.data_dir = kwargs.get("data_dir", BASE_DIR / "tools" / "gcl" / "data")
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)
        # `jurisdictions.json` contains all U.S. states, territories and federal/state court names,
        # codes, and abbreviations.
        self.jurisdictions = kwargs.get(
            "jurisdictions", load_json(self.data_dir / "jurisdictions.json", True)
        )
        # Will be used to label all folders inside `data_dir`.
        self.suffix = kwargs.get("suffix", "")
        self.court_codes = sorted(
            [k for k in self.jurisdictions["court_details"].keys()],
            key=len,
            reverse=True,
        )
        # `reporters.json` contains reporters with different variations/flavors mapped to their standard form.
        self.reporters = kwargs.get(
            "reporters", load_json(self.data_dir / "reporters.json", True)
        )
        # `months.json` contains a dictionary that maps abbreviations/variations of months to their full names.
        self.months = kwargs.get(
            "months", load_json(self.data_dir / "months.json", True)
        )
        # USPTO scraper of transactions history between examiner and appellant including ptab decisions.
        # This is needed if the appellant is not satisfied with the decision and seeks to appeal to the federal court.
        self.uspto = USPTOscrape(suffix=self.suffix)

    @property
    def case(self):
        if self._case is None:
            self._case = {
                "id": None,
                "full_case_name": None,
                "case_numbers": [],
                "citation": None,
                "short_citation": [],
                "first_page": None,
                "last_page": None,
                "cites_to": {},
                "date": None,
                "court": {},
                "judges": [],
                "personal_opinions": {},
                "patents_in_suit": [],
                "html": None,
                "training_text": None,
                "footnotes": [],
            }
        return self._case

    @property
    def prioritize_citations(self):
        """
        Sort citations in a gcl file based on priorities. If a citation has party names,
        plaintiffs will be given a `0`, and defendants will be labeled with a `1`.
        Otherwise, `2` will be used.
        """
        if not self._prioritize_citations:
            citations = reduce(
                concat,
                [
                    [(key, var["citation"], 2) for var in c["variations"]]
                    for key, val in self.case["cites_to"].items()
                    for c in val
                ],
                [],
            )

            for name in citations:
                if nm := regex(
                    name[1], [(r"^(.*?) v\.? (.*)", "")], sub=False, flags=re.I
                ):
                    citations += [(name[0], nm[0][i], i) for i in (0, 1)]

            # Sort citations bsaed on priority (plaintiffs > defendants > plaintiffs v. defendants)
            self._prioritize_citations = sorted(citations, key=lambda x: x[2])

        return self._prioritize_citations

    def gcl_patent_data(
        self, number_or_url: str, case_id=None, skip_patent=False, return_data=False
    ):
        """
        Download and scrape data for a patent with Patent (Application) No. or valid url `number_or_url`.

        Example
        -------
        >>> gcl_patent_data('https://patents.google.com/patent/US20150278825A1/en')

        Args
        ----
        :param skip_patent: ---> bool: if true, skips downloading patent and rather looks for
                                 a local patent file under `patents` folder.
        :param return_data: ---> bool: if true, returns the serialized downloaded data.
        """
        [patent_number, url] = [""] * 2
        info = {
            "patent_number": patent_number,
            "url": url,
            "title": None,
            "abstract": None,
            "claims": {},
        }
        subfolder = case_id

        if case_id:
            info["case_id"] = case_id

        else:
            subfolder = patent_number

        found = False

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
                info = load_json(json_path)
            found = True

        else:
            if not skip_patent:
                url = f"https://patents.google.com/patent/{patent_number}"
                status, html = self._get(url)
                if status == 200:
                    found = True
                    patent = BS(deaccent(html), "html.parser")
                    claim_tags = patent.select(".claims > *")
                    last_independent_num = 1
                    extra_count = 0
                    relevant_patterns = [*self.strip_patterns, *self.space_patterns]
                    for tag in claim_tags:
                        in_tag = tag.find(
                            lambda tag: tag.name == "div" and tag.attrs.get("num", None)
                        )
                        if in_tag:
                            num = in_tag.attrs["num"]
                            if regex(num, [(r"\d$", "")], sub=False):
                                if "-" in num:
                                    if not regex(num, [(r"\d+-\d+", "")], sub=False):
                                        extra_count += (
                                            1  # Fixes wrong counting of claims.
                                        )
                                    num = int(regex(num, [(r"-.*$", "")])) + extra_count
                                else:
                                    num = int(num) + extra_count
                                context = regex(
                                    tag.get_text(),
                                    [*relevant_patterns, (r"^\d+\. ", "")],
                                )
                                attach_data = {
                                    "claim_number": num,
                                    "context": context,
                                    "dependent_on": None,
                                }
                                info["claims"][num] = attach_data
                                if "claim-dependent" not in tag.attrs["class"]:
                                    last_independent_num = num

                                else:
                                    if num > 1:
                                        if fn := regex(
                                            context,
                                            [(r"\s+claim\s+(\d+)", "")],
                                            sub=False,
                                            flags=re.I,
                                        ):
                                            last_independent_num = int(fn[0])

                                        info["claims"][num][
                                            "dependent_on"
                                        ] = last_independent_num

                    abstract_tags = patent.find_all("div", class_="abstract")
                    abstract = " ".join(
                        [
                            regex(ab.get_text(), relevant_patterns)
                            for ab in abstract_tags
                        ]
                    )
                    info["abstract"] = abstract
                    info["title"] = regex(
                        patent.find("h1", attrs={"itemprop": "pageTitle"}).get_text(),
                        [*relevant_patterns, (r" - Google Patents|^.*? - ", "")],
                    )
                    info["url"] = url
                    info["patent_number"] = patent_number
                    if info["title"] and info["claims"]:
                        print(f"Saving patent data for Patent No. {patent_number}...")
                        create_dir(json_path.parent)
                        with open(json_path.__str__(), "w") as f:
                            json.dump(info, f, indent=4)

        if return_data:
            if not found:
                return found, []

            if not info["title"]:
                if patent_number:
                    if skip_patent:
                        print(
                            f"Patent No. {patent_number} has not been downloaded yet. Please set `skip_patent=False`"
                        )
                    else:
                        print(
                            f"Invalid patent number detected; saving Patent No. {patent_number} stopped"
                        )
                return found, []

            if not info["claims"]:
                print(
                    f"Invalid patent number detected; saving Patent No. {patent_number} stopped"
                )
                return found, []

            return found, info["claims"]

    def gcl_citation_summary(self, case_id, suffix=None, return_list=True):
        """
        Given a `case_id` for a gcl page, create a summary of the case in terms
        of its bluebook citation, court and date. If case is not found in the local
        database, download it first.

        Args
        ----
        :param suffix: ---> str: overwrites instance attribute `suffix`.
        :param return_list: ---> bool: if False, return a dictionary instead with keys being
                                 `citation`, `court` and `date`.
        """
        data = {"citation": None, "court": None, "date": None}

        if not suffix:
            suffix = self.suffix

        path_to_file = (
            create_dir(self.data_dir / "json" / f"json_{suffix}") / f"{case_id}.json"
        )

        url = self.base_url + f"scholar_case?case={case_id}"

        if not path_to_file.is_file():
            print(f"Now downloading the case {case_id}...")
            s1 = self.suffix
            self.suffix = suffix
            data = self.gcl_parse(url, return_data=True, random_sleep=True)
            self.suffix = s1

        else:
            data = load_json(path_to_file)

        case_summary = []
        if not return_list:
            case_summary = {case_id: {}}

        if data:
            data["url"] = url
            for key, val in data.items():
                if key in ["citation", "date", "court", "url"]:
                    if return_list:
                        if key == "court":
                            case_summary += val.values()
                        else:
                            case_summary.append(val)
                    else:
                        case_summary[case_id][key] = val
        return case_summary

    def gcl_long_blue_cite(self, citation):
        """
        Return longest bluebook version of a citation by removing pages and extra details.
        Return None if the citation does not match any of `long_bluebook_patterns`.

        Example
        -------
        >>> citation = "Ormco Corp. v. Align Tech., Inc., 463 F.3d 1299, 1305 (Fed. Cir. 2006)"
        u"Ormco Corp. v. Align Tech., Inc., 463 F.3d 1299 (Fed. Cir. 2006)"

        """
        citation = regex(citation, self.extras_citation_patterns, flags=re.I)

        if regex(citation, self.long_bluebook_patterns, sub=False, flags=re.I):
            return citation
        return

    def _collect_cites(self, data: str) -> list:
        """
        Collect all the citations in a gcl `data`. If file is not found,
        it will be downloaded.

        Args
        ----
        :param data: ---> str or pathlib: path to a gcl json file or a valid case ID.
        """
        case_repo, case_id = {}, ""
        if isinstance(data, str):
            if regex(data, self.just_number_patterns, sub=False):
                top_folder = self.data_dir / f"json_{self.suffix}"
                for folder in top_folder.glob("**"):
                    json_path = top_folder / folder / f"{data}.json"
                    if json_path.is_file():
                        case_repo = load_json(json_path)
                        break

                if not case_repo:
                    case_id = data
                    url = self.base_url + f"scholar_case?case={case_id}"
                    case_repo = self.gcl_parse(url, return_data=True)

        if isinstance(data, Path):
            case_repo = load_json(data)
            case_id = case_repo["id"]

        cites = {}
        for k, v in case_repo["cites_to"].items():
            cites[k] = reduce(
                concat, [[var["citation"] for var in i["variations"]] for i in v], []
            )

        cites[case_id] = [case_repo["citation"]]
        return cites

    def _fix_abbreviations(self, citation):
        """
        Fix court and date abbreviations in a `citation` due to gcl processing
        issues or non-bluebook adaptations.
        """
        if fn := regex(citation, self.approx_court_location_patterns, sub=False):
            if gn := regex(fn[0], self.date_patterns, sub=False):
                date = shorten_date(datetime.strptime(gn[0], "%B %d, %Y"))
                citation = citation.replace(gn[0], date)
            return citation.replace(fn[0], regex(fn[0], self.court_clean_patterns))

        return citation

    def gcl_parse(
        self,
        path_or_url: str,
        skip_patent=False,
        return_data=False,
        need_proxy=False,
        random_sleep=False,
    ):
        """
        Parses a Google case law page (gcl) under an `html_path` or at a `url`
        and serializes/saves all relevant information to a json file.

        Args
        ----
        :param path_or_url: ---> str: a path to an html file or a valid url of a gcl page.
        :param skip_patent: ---> bool: if true, skips downloading and scraping patent information.
        :param random_sleep: ---> bool: if True, sleep for randomly selected seconds before making
                                        a new request.
        """
        html_text = ""
        if not Path(path_or_url).is_file():
            html_text = tuple(self._get(path_or_url, need_proxy))[1]
            if random_sleep:
                sleep(randint(2, 10))
        else:
            with open(path_or_url, "r") as f:
                html_text = f.read()
        self.html = BS(deaccent(html_text), "html.parser")
        self._opinion(path_or_url)

        if not self.opinion:
            return self.case

        self._get_id()
        self._replace_footnotes()
        self._full_casename()
        self._pages()
        self._short_citation()
        self._consolidate_broken_tags()
        self._replace_a_tags()
        self.gcl_get_date()
        self._citation_details()
        self.gcl_get_judge()
        self._patents_in_suit(skip_patent)
        self._serialize_footnotes()
        self._replace_generic_tags()
        self._training_text()
        self._personal_opinion()

        with open(
            str(
                create_dir(self.data_dir / "json" / f"json_{self.suffix}")
                / f"{self.case['id']}.json"
            ),
            "w",
        ) as f:
            json.dump(self.case, f, indent=4)

        if return_data:
            return self.case

        self._case = None
        return

    def gcl_get_judge(self, html=None, court_code=None, just_locate=False):
        """
        Extract judges' names from the `html` of the opinion page.

        Args
        ----
        :param html: ---> BeautifulSoup object corresponding to html of the opinion page.
        :param court_code: ---> str: the court code to have further control on the parsed judge data.
        :param just_locate: ---> bool: just locate the tag containing judge names and return.
        """

        if not html:
            html = self.opinion

        initial_cleaning_patterns = [
            *self.page_patterns,
            *self.clean_footnote_patterns,
            *self.judge_clean_patterns_1,
        ]
        judge_tag = ""

        for tag in html.find_all("p"):
            if not tag.find("h2"):
                tag_text = regex(tag.get_text(), initial_cleaning_patterns)
                if regex(tag_text, self.judge_patterns, sub=False):
                    judge_tag = tag
                    break

        if just_locate:
            return judge_tag

        if not court_code:
            court_code = self.case["court"].get("court_code", None)

        # Exclude the Supreme Court judges as it is not so useful.
        judges = []
        if judge_tag and court_code not in ["us"]:
            judges = regex(judge_tag.get_text(), initial_cleaning_patterns)
            judges = regex(
                "".join(
                    regex(
                        judges,
                        [
                            *self.judge_clean_patterns_2,
                            (" and ", ", "),
                            *self.extra_char_patterns,
                            *self.judge_clean_patterns_3,
                        ],
                        flags=re.I,
                    )
                ).split(","),
                [*self.comma_space_patterns, (r":", "")],
            )

            for i, person in enumerate(judges):
                if regex(person, self.roman_patterns, sub=False) or regex(
                    person, self.abbreviation_patterns, sub=False
                ):
                    judges[i - 1] = f"{judges[i-1]}, {person}"
                    judges.pop(i)
                elif not person:
                    judges.pop(i)

            judges = regex(
                [
                    " ".join(
                        [
                            l.lower().capitalize()
                            if not regex(l, self.roman_patterns, sub=False)
                            else l
                            for l in name.split()
                        ]
                    )
                    for name in [j for j in judges if j]
                ],
                [
                    (
                        r"(?<=[\'’])\w|\b[a-z]+(?=\.)",
                        lambda match: f"{match.group(0).capitalize()}",
                    )
                ],
            )

        self.case["judges"] = judges
        return judges

    def gcl_citor(self, data=None):
        """
        Create a bluebook citation for a given input html, url or path to an html file
        of a gcl page.

        Args
        ----
        :param data: ---> str, BeautifulSoup obj: A url, path to the Google
                          case law page or its case ID or its BeautifulSoup object.
                          Defaults to `self.html`.
        """
        html, html_text = "", ""

        if not data:
            data = self.html

        if isinstance(data, BS):
            html = data

        else:
            if not Path(data).is_file():
                html_text = tuple(self._get(data))[1]
            else:
                with open(data, "r") as f:
                    html_text = f.read()

            html = BS(html_text, "html.parser")

        citation = regex(html.find(id="gs_hdr_md").get_text(), self.extra_char_patterns)
        [court_name, court_type, state] = [""] * 3
        try:
            cdata = regex(citation, self.federal_court_patterns, sub=False)
            if not cdata:
                citation = regex(citation, [(r" ?[,-] ((\d{4}))$", r" (\g<1>)")])
                return citation, "Supreme Court"
            else:
                cdata = cdata[0]
            delimiter, court_name, year = cdata[1:]

            # Dist. Court by itself is vague. It defaults to District Court of D.C. or D.D.C.
            # E.g. x v. y, Dist. Court ---> x v. y, D.D.C.
            if court_name in ["Dist. Court"]:
                court_name = "D.D.C."
            else:
                fn = self.jurisdictions["federal_courts"].get(court_name, None)
                if fn is not None:
                    court_name = fn
                else:
                    # Fixes a district court that is only the state name.
                    # E.g. x v. y, Dist. Court, North Carolina ---> x v. y, D.N.C.
                    possible_court_type = regex(
                        citation.replace(cdata[0], "").split(",")[-1],
                        self.space_patterns,
                    )
                    state_abbr = self.jurisdictions["states_territories"][court_name]
                    if "Dist." in possible_court_type and state_abbr:
                        court_name = (
                            f"D. {state_abbr}"
                            if regex(state_abbr, [(r"[a-z]", "")], sub=False)
                            else f"D.{state_abbr}"
                        )
                    else:
                        raise KeyError

            court_name_spaced = f"{court_name} " if court_name else ""
            if not court_name:
                case_number = "" if delimiter == "-" else f", No. XXXXXX"
                date = year if delimiter == "-" else self.gcl_get_date(html, True)
                citation = regex(
                    citation.replace(
                        cdata[0], f"{case_number} ({court_name_spaced}{date})"
                    ),
                    self.strip_patterns,
                )
                return citation, "Supreme Court"

            # If Fed. Cl. and D.D.C. appear in a citation, add a placeholder ', Federal Courts'
            # to continue using the following lines without having to modify the regex.
            # E.g. x v. y, No 2021-2344 (Fed. Cl. 2021) ---> x v. y, No 2021-2344, Federal Courts (Fed. Cl. 2021)
            replace_with = (
                f" ({court_name_spaced}{year})"
                if court_name not in ["Fed. Cl.", "D.D.C."]
                else f", Federal Courts ({court_name_spaced}{year})"
            )
            citation = regex(
                citation.replace(cdata[0], replace_with), self.strip_patterns
            )
            cdata = regex(
                citation,
                [(r"( ?([-,]) ([\w:. \']+) \(([\w:. \']+)\))$", "")],
                sub=False,
            )[0]

            delimiter, court_type = cdata[1:3]
            court_type = self.jurisdictions["federal_courts"][court_type]
            court_type_spaced = f"{court_type} " if court_type else ""
            # Encountering a dash after publication in Google cases means that the case has been published.
            # So no case number is needed according to bluebook if a dash is encountered.
            case_number = "" if delimiter == "-" else f", No. XXXXXX"
            date = year if delimiter == "-" else self.gcl_get_date(html, True)
            citation = regex(
                citation.replace(
                    cdata[0],
                    f"{case_number} ({court_type_spaced}{court_name_spaced}{date})",
                ),
                self.strip_patterns,
            )

        except KeyError:
            [court_name, state, year] = [""] * 3
            cdata = regex(citation, self.state_court_patterns, sub=False)
            if not cdata:
                citation = regex(citation, [(r" ?[,-] ((\d{4}))$", r" (\g<1>)")])
                return citation, "Supreme Court"
            else:
                cdata = cdata[0]

            delimiter = ""
            for i, c in enumerate(cdata):
                if i == 1:
                    delimiter = c
                if i == 2:
                    state = regex(
                        c, [(r"\.", ""), (r"([A-Z-a-z])(?=[A-Z]|\b)", r"\g<1>.")]
                    )
                    # States which don't get abbreviated:
                    if c in ["Alaska", "Idaho", "Iowa", "Ohio", "Utah"]:
                        state = c
                elif i == 3:
                    d = c.split(",")[0]
                    court_name = self.jurisdictions["state_courts"][d]
                    # New York Supreme Court is cited as 'N.Y. Sup. Ct.'
                    if state == "N.Y." and d == "Supreme Court":
                        court_name = "Sup. Ct."
                elif i == 4:
                    year = c

            state_spaced = "" if "Commw" in court_name else f"{state} "
            court_name_spaced = f"{court_name} "
            case_number = "" if delimiter == "-" else f", No. XXXXXX"
            date = year if delimiter == "-" else self.gcl_get_date(html, True)
            citation = regex(
                citation.replace(
                    cdata[0], f"{case_number} ({state_spaced}{court_name_spaced}{date})"
                ),
                self.strip_patterns,
            )
        return citation, regex(
            " ".join([state, court_type, court_name]),
            [*self.space_patterns, *self.strip_patterns],
        )

    def gcl_get_date(self, html=None, short_month=False):
        """
        Extract the decision date for the `html` of court opinion with
        the format `Day Month, Year` format and convert it to `Year-Month-Day`.

        Args
        ----
        :param short_month: ---> bool: if true, returns the date like `%b. %d, %Y`.
        """
        __ = False
        if not html:
            __ = True
            html = self.opinion

        date = regex(
            html.find_all(
                lambda tag: tag.name == "center"
                and regex(tag.get_text(), self.date_patterns, sub=False)
            )[-1].get_text(),
            self.date_patterns,
            sub=False,
        )[0]

        date_object = datetime.strptime(regex(date, self.space_patterns), "%B %d, %Y")
        date_string = date_object.strftime("%Y-%m-%d")

        if short_month:
            date_string = shorten_date(date_object)

        if __:
            self.case["date"] = date_string
            return

        return date_string

    def gcl_bundle_cites(self, blue_citation=False):
        """
        Bundle citations collected using the method `_collect_cites`
        from each case found in the subdirectory `~/data/json/json_suffix`
        and save them to `~/data/json/citations_suffix.json`. Use a file
        at `~/data/json/manual_cites_suffix.json` with a data structure
        compatible with `~/data/json/citations_suffix.json` to consider
        overwriting imperfect citations.

        Args
        ----
        :param blue_citation: ---> bool: if True, returns the long bluebook version of the citation.
                                         Returns None if nothing is found.
        """
        json_folder = self.data_dir / "json"
        cites = json_folder / f"citations_{self.suffix}.json"
        paths = (json_folder / f"json_{self.suffix}").glob("*.json")

        # Load json file that contains case IDs that have encountered 404 error.
        cases_404 = load_json(json_folder / f"404_{self.suffix}.json")

        # Load json file that contains manually added citations.
        manual_cites = load_json(json_folder / f"manual_cites_{self.suffix}.json")

        r = {}

        collected_cites = list(
            multi_run(
                self._collect_cites,
                list(paths),
                threading=True,
                yield_results=True,
            )
        )

        for c in tqdm(collected_cites, total=len(collected_cites)):
            for k, v in c.items():
                if r.get(k, None):
                    r[k] += v
                else:
                    r[k] = v

        def _apply(c, k, extras=True):
            if extras:
                c = self._fix_abbreviations(regex(c, self.extras_citation_patterns))
            if c:
                r[k] = {**r[k], **self._tokenize_citation(c)}

        def _longest_cite(k):
            """
            Out of many variations of a citation in the `cites_to` key of gcl files,
            pick the longest one and tokenize it using the `_apply` function.
            """
            value = sorted(r[k], key=len, reverse=True)

            r[k] = {
                "citation": value[0],
                **{
                    m: None
                    for m in [
                        "citation_details",
                        "case_name",
                        "published",
                        "date",
                        "docket_numbers",
                        "court",
                    ]
                },
                "needs_review": False,
            }
            match = False
            if blue_citation:
                for v in value:
                    if citation := self.gcl_long_blue_cite(v):
                        _apply(self._fix_abbreviations(citation), k, False)
                        match = True
                        break

                if fn := manual_cites.get(k, None):
                    _apply(fn["citation"], k)

                else:
                    if not match:
                        if not cases_404.get(k, None):
                            summary = self.gcl_citation_summary(
                                k, f"cites_{self.suffix}", False
                            )
                            if fn := summary[k]:
                                _apply(fn["citation"], k)
                        else:
                            r[k]["needs_review"] = True

                if not r[k]["case_name"] or r[k]["case_name"] not in r[k]["citation"]:
                    r[k]["needs_review"] = True

        list(multi_run(_longest_cite, r.keys(), threading=True, pathos=True))

        with open(cites.__str__(), "w") as f:
            json.dump(r, f, indent=4)

        return

    def gcl_make_list(self, filename):
        """
        Create a csv file that contains existing case summaries in
        `json_suffix` and save it under `~/data/csv/{filename}.csv.`
        """
        case_files = (self.data_dir / "json" / f"json_{self.suffix}").glob("*.json")
        case_summaries = list(
            multi_run(
                self.gcl_citation_summary,
                [f.stem for f in case_files],
                yield_results=True,
            )
        )
        case_summaries.sort(
            key=lambda x: datetime.strptime(x[1], "%Y-%m-%d"), reverse=True
        )
        case_summaries = [[i + 1, *entry] for i, entry in enumerate(case_summaries)]
        with open(self.data_dir / "csv" / f"{filename}.csv", "w", newline="") as f:
            csvfile = writer(f, quoting=QUOTE_ALL, lineterminator="\n", delimiter="\t")
            csvfile.writerow(
                [
                    "  #  ",
                    "Case",
                    "Date",
                    "Court Full Name",
                    "Court Short Name",
                    "Court Code",
                    "Jurisdiction",
                    "URL",
                ]
            )
            csvfile.writerows(case_summaries)

        return

    def gcl_drop(
        self,
        remove_redundant=False,
        remove_patent=False,
        external_list=None,
    ):
        """
        Show the redundant (unpublished) cases. Only keep the published ones
        if `keep_published` is set to True. Add an arbitrary `external_list`
        to the bunch of cases to be removed.

        Args
        ----
        :param remove_redundant: ---> bool: if True, will remove the serialized data and
                                            patent information of the redundant (unpublished) cases.
        :param external_list: ---> list: an arbitrary list of case IDs whose serialized data are found
                                         in `json_suffix`, which too need to be removed.
        :param remove_patent: ---> bool: if True, remove patent data.
        """
        directory = self.data_dir / "json" / f"json_{self.suffix}"
        json_files = list((directory).glob("*.json"))

        name_patterns, docket_patterns, ids = [], [], []
        for f in tqdm(json_files, total=len(json_files)):
            info = load_json(f)
            dc = [info["date"]] + [info["court"]["court_code"]]
            name_patterns += ["".join([info["full_case_name"].lower()] + dc)]

            docket_patterns += [
                "".join(
                    ["".join(c["docket_number"]).lower() for c in info["case_numbers"]]
                    + dc
                )
            ]

            ids += [""] if info["short_citation"] else [info["id"]]

        patterns = name_patterns + docket_patterns
        indices = [
            fn
            for value in set(patterns)
            if len(fn := [i for i, v in enumerate(patterns) if v == value]) > 1
        ]
        ids.extend(ids)
        repeated_ids = set([ids[i] for i in set(reduce(concat, indices, [])) if ids[i]])
        print(f"There are {len(repeated_ids)} repeated cases in {str(directory)}")

        def _remove_data(case_id, label):
            """Remove all data related to the case ID `case_id` from the `data` folder."""
            path = directory / f"{case_id}.json"

            if path.is_file():
                path.unlink()

            if remove_patent:
                patent_folder = (
                    self.data_dir / "patent" / f"patent_{self.suffix}" / case_id
                )
                if patent_folder.is_dir():
                    rm_tree(patent_folder)

            print(f"Case data with ID {case_id} ({label}) was removed successfully")

        if remove_redundant:
            print("Starting to remove redundant (unpublished) cases...")
            list(
                _remove_data(case_id, "redundant")
                for case_id in tqdm(repeated_ids, total=len(repeated_ids))
            )

        else:
            redundant_cases = {
                x: self.gcl_citation_summary(x, False)[x] for x in repeated_ids
            }
            print(f"Redundant cases: {redundant_cases}")

        if external_list:
            print("Starting to remove cases with IDs stored in external list...")
            list(
                _remove_data(case_id, "external")
                for case_id in tqdm(external_list, total=len(external_list))
            )

        return

    def _get(self, url_or_id, need_proxy=False):
        """
        Request to access the content of a Google Scholar case law page with a valid `url_or_id`.

        Args
        ----
        :param need_proxy: ---> bool: if True, start switching proxy IP after each request
                                      to reduce risk of getting blocked.
        """
        url = url_or_id
        if regex(url_or_id, self.just_number_patterns, sub=False):
            url = self.base_url + f"scholar_case?case={url_or_id}"

        res_content = ""

        if need_proxy:
            proxy = proxy_browser()
            proxy.get(url)
            res_content = proxy.page_source
            status = 200

            if not res_content:
                status = 0

            else:
                # Obtain a `404` error indicator if server returned html.
                if regex(res_content, [(r"class=\"gs_med\"", "")], sub=False):
                    status = 404
                # Solve recaptcha if encountered.
                elif regex(res_content, [(r"id=\"gs_captcha_c\"", "")], sub=False):
                    EXPECTED_RESULT = "You are verified"
                    recaptcha = recaptcha_process(url, proxy)
                    assert EXPECTED_RESULT in recaptcha
                switch_ip()

        else:
            response = requests.get(url)
            response.encoding = response.apparent_encoding
            status = response.status_code
            if status == 200:
                res_content = response.text

        if status == 404:
            print(f'URL "{url}" not found')

        if status not in [200, 404]:
            raise Exception(f"Server response: {status}")

        return status, res_content

    def _opinion(self, path_or_url):
        """
        Get the opinion text from `path_or_url` to a gcl document.
        """
        self.opinion = self.html.find(id="gs_opinion")

        # Return empty set if case law page was not found (`404` error).
        # Store the case ID with a `404` error.
        if not self.opinion:
            print(f'Serialization failed for "{path_or_url}"')
            path_404 = self.data_dir / "json" / f"404_{self.suffix}.json"
            not_downloaded = load_json(path_404)
            with open(path_404.__str__(), "w") as f:
                case_id = regex(
                    path_or_url, [(r"(?:.*scholar_case\?case=)?(\d+)(?:.*)?", r"\g<1>")]
                )
                not_downloaded[case_id] = case_id
                json.dump(not_downloaded, f, indent=4)
            return {}

        self.opinion.find(id="gs_dont_print").replaceWith("")
        self.case["html"] = self.opinion.__str__()
        self.links = self.opinion.find_all("a")
        return

    def _get_id(self):
        """
        Retrieve the case ID given the html of the case file.
        """
        self.case["id"] = regex(
            str(self.html.find(id="gs_tbar_lt")), self.case_patterns, sub=False
        )[0]
        return

    def _replace_footnotes(self):
        """
        Obtain all the footnote IDs cited in the text and replace them with
        a unique identifier '@@@@[id]' for tracking purposes.
        """
        footnote_identifiers = self.opinion.find_all(
            lambda tag: tag.name == "sup" and tag.find("a")
        )
        if footnote_identifiers:
            for tag in footnote_identifiers:
                if tag.parent.attrs and tag.parent.attrs["id"] == "gsl_case_name":
                    tag.replaceWith("")
                    self.opinion.find_all("small")[-1].find(
                        lambda tag: tag.name == "p" and tag.find("a", class_="gsl_hash")
                    ).replaceWith("")
                else:
                    tag.replaceWith(
                        f" {self.footnote_label}{tag.find('a').attrs['name'].replace('r', '')} "
                    )
        return

    def _full_casename(self):
        """
        Extract full case name from the opinion.
        """
        gsl_case_name = self.opinion.find(id="gsl_case_name")
        self.case["full_case_name"] = regex(
            gsl_case_name.get_text(),
            [*self.strip_patterns, *self.comma_space_patterns],
        )
        gsl_case_name.replaceWith("")
        return

    def _pages(self):
        """
        Extract the first and last page of the opinion, if published.
        """
        if page_nums := self._page_number_tags():
            pages = [p.get_text() for p in page_nums]
            self.case["first_page"], self.case["last_page"] = int(pages[0]), int(
                pages[-1]
            )
        return

    def _page_number_tags(self):
        """
        Find all the tags containing page numbers.
        """
        return self.opinion.find_all("a", class_="gsl_pagenum")

    def _short_citation(self):
        """
        Extract short citation(s) of the case, if published.
        """
        for center in self.opinion.select("center > b"):
            self.case["short_citation"].append(center.get_text())
            center.replaceWith("")
        return

    def _casenumber(self, html=None, only_casenumber=False):
        """
        Extract the case IDs and docket numbers of any case related
        to `html` of the opinion document.

        Args
        ----
        :param only_casenumber: ---> bool: if True, return only the case numbers.
        """

        if not html:
            html = self.opinion

        case_num = html.select_one("center > a")
        case_ids_ = [""]
        if fn := case_num.attrs:
            case_ids_ = regex(fn["href"], self.casenumber_patterns, sub=False)[0].split(
                "+"
            )

        docket_numbers = []

        court_code = self.case["court"].get("court_code", None)
        jurisdiction = self.case["court"].get("jurisdiction", None)

        if jurisdiction == "F":
            if court_code:
                if court_code not in ["us"]:
                    docket_numbers = regex(
                        case_num.get_text(), self.docket_appeals_patterns, sub=False
                    )
                elif court_code in ["us"]:
                    docket_numbers = regex(
                        case_num.get_text(), self.docket_us_patterns, sub=False
                    )

        if not docket_numbers:
            docket_numbers = regex(
                case_num.get_text(),
                [
                    (self.docket_clean_patterns, ""),
                    (r"\([\w ]+\)", ""),
                    (r",? +and +", ","),
                ],
                flags=re.I,
            ).split(",")

        docket_numbers = regex(docket_numbers, self.extra_char_patterns)
        # Correct the docket numbers if they start with '-'
        for i, d in enumerate(docket_numbers):
            if d.startswith("-"):
                docket_numbers[i] = f'{docket_numbers[i-1].split("-")[0]}{d}'

        if only_casenumber:
            return docket_numbers

        dn = len(docket_numbers)
        ci = len(case_ids_)
        if dn > ci:
            return zip(case_ids_ * (dn - ci + 1), docket_numbers)

        return zip(case_ids_, docket_numbers)

    def _consolidate_broken_tags(self):
        """
        Consolidate broken <i> tags or double <a> tags created due to page numbers.
        """
        for a in self._page_number_tags():
            if fn := a.previous_sibling:
                # Fix <a>A</a> page number <a>B</a> into <a>AB</a> page number
                if (
                    fn.name == "a"
                    and fn.attrs["href"]
                    and "scholar_case?" in fn.attrs["href"]
                ):
                    if gn := a.next_sibling.next_sibling:
                        if (
                            gn.name == "a"
                            and gn.attrs["href"]
                            and gn.attrs["href"] == fn.attrs["href"]
                        ):
                            if zn := gn.i:
                                zn.unwrap()
                                gn.smooth()
                            gn.string = regex(fn.get_text() + gn.text, [(r" +", " ")])
                            fn.decompose()

                # Consolidate <i>A</i> page number <i>B</i> into <i>AB...</i> page number.
                if gn := fn.previous_sibling:
                    if gn.name == "i":
                        if regex(fn, [(r"^ +$", "")], sub=False):
                            if dn := a.next_sibling:
                                if regex(dn, [(r"^ +$", "")], sub=False):
                                    if dn.next_sibling:
                                        if cn := dn.next_sibling.next_sibling:
                                            if cn.name == "i":
                                                gn.string = regex(
                                                    f"{gn.text} {cn.get_text()}",
                                                    [(r" +", " ")],
                                                )
                                                cn.decompose()

        # Consolidate <i>A</i> <i>B</i> into <i>AB...</i>.
        for i in self.opinion.find_all("i"):
            next_tag = i.next_sibling

            if isinstance(next_tag, NavigableString):
                next_tag = next_tag.next_sibling
                if (
                    regex(i.next_sibling, [(r"^ +$", "")], sub=False)
                    and next_tag
                    and next_tag.name == "i"
                ):
                    next_tag.string = regex(
                        i.get_text() + i.next_sibling + next_tag.text, [(r" +", " ")]
                    )
                    i.decompose()
        return

    def _replace_a_tags(self):
        """
        Replace every valid citation within the case wrapped in <a> tags
        linking to a gcl page with a unique ID and collect the citation.
        """
        cites = {}
        for i, l in enumerate(self.links):
            c = f"[{i + 1}]"
            if fn := l.attrs:
                if fn.get("href", None) and "/scholar_case?" in fn["href"]:
                    case_citation = regex(l.get_text(), self.extra_char_patterns)
                    case_name = None
                    if gn := l.find("i"):
                        case_name = regex(gn.get_text(), self.comma_space_patterns)
                    id_ = regex(l.attrs["href"], self.case_patterns, sub=False)[0]

                    # The key `identifier` may be used to trace different variations of
                    # the same citation in the case text specially when substituting a
                    # case ID with its citation. E.g. #123456789[identifier].
                    var = {"citation": case_citation, "identifier": c}
                    ct = {
                        "case_name": case_name,
                        "variations": [var],
                    }
                    if not cites:
                        cites = {id_: [ct]}
                    else:
                        if cites.get(id_, None):
                            cite_data = cites[id_]
                            not_accounted = True
                            for el in cite_data:
                                if el["case_name"] == case_name:
                                    variants = [v["citation"] for v in el["variations"]]
                                    if case_citation not in variants:
                                        el["variations"] += [var]
                                    else:
                                        c = el["variations"][
                                            variants.index(case_citation)
                                        ]["identifier"]
                                    not_accounted = False
                                    break

                            # If some variation of a citation does not exist in the cited cases already:
                            if not_accounted:
                                cite_data += [ct]
                        else:
                            cites[id_] = [ct]

                    # Change <i>A</i> to <em>A</em> if it is adjacent to an <a> tag.
                    # This will avoid allowing replacement of broken <i> tags with
                    # citation label later.
                    for adjacent in [l.next_sibling, l.prev_sibling]:
                        if adjacent and adjacent.name == "i":
                            adjacent.name = "em"

                    l.replaceWith(f" {self.citation_label}{id_}{c} ")

        self.case["cites_to"] = cites
        return

    def _citation_details(self):
        """
        Extract and serialize citation details such as case citation,
        court information, and case number(s).
        """
        self.case["citation"], court_info = self.gcl_citor()
        self.case["court"] = self.jurisdictions["court_details"][court_info]

        # Insert the case number if the case is still unpublished
        self.case["citation"] = self.case["citation"].replace(
            "XXXXXX", self._casenumber(self.html, True)[0]
        )

        # Serialize case numbers.
        for id_, num_ in self._casenumber():
            if fn := self.case["case_numbers"]:
                for el in fn:
                    if id_ == el["id"]:
                        el["docket_number"].append(num_)
                    else:
                        self.case["case_numbers"].append(
                            {"id": nullify(id_), "docket_number": [num_]}
                        )
                        break
            else:
                self.case["case_numbers"].append(
                    {"id": nullify(id_), "docket_number": [num_]}
                )
        return

    def _replace_i_tags(self, html):
        """
        Replace those <i> tags in `html` not inside an <a> tag with citation label + num
        if the content of <i> tag is inside the corresponding case name/citation.
        """
        for case_name in self.prioritize_citations:
            for i in html.find_all("i"):
                i_tag = regex(i.get_text(), self.boundary_patterns)
                cleaned_i_tag = regex(i_tag, [(r"[,.]+$", "")])

                if (
                    i_tag
                    and regex(
                        case_name[1],
                        [(r"\b" + re.escape(cleaned_i_tag) + r"\b", "")],
                        sub=False,
                    )
                    and len(i_tag) > 2
                    and cleaned_i_tag not in ["id", "Id"]
                    and not regex(cleaned_i_tag, self.boundary_patterns, sub=False)
                ):

                    end_character = ""
                    for end in [".", ",", "'s"]:
                        if i_tag.endswith(end):
                            end_character = end
                    i.replaceWith(
                        f" {self.citation_label}{case_name[0]} {end_character}"
                    )
        return

    def _get_claim_numbers(self):
        """
        Extract the claim numbers cited in a gcl court case from
        patents that are involved in the lawsuit.
        """
        small_tag = self.opinion.find_all("small")
        footnotes_data, footnote_tags = {}, []
        if small_tag:
            footnotes = small_tag[-1].find_all("a", class_="gsl_hash")
            for tag in footnotes:
                parent_tag = tag.parent
                footnote_tags.append(tag.parent)
                tag.parent.replaceWith("")
                footnotes_data[tag.attrs["name"]] = regex(
                    parent_tag.get_text(), self.space_patterns
                )

        # Remove page numbers and well as line-breakers.
        modified_opinion = regex(
            self.opinion.get_text(),
            [(r" \d+\*\d+ ", " "), *self.page_patterns, *self.strip_patterns],
        )

        # Append the footnote tags back to the opinion.
        for tag in footnote_tags:
            self.opinion.small.append(tag)

        # Bring the footnote context in the text for keeping continuity.
        for key, val in footnotes_data.items():
            modified_opinion = modified_opinion.replace(
                f"{self.footnote_label}{key}", val
            )

        # Patent numbers should be extracted here to include those cited in the footnotes.
        self._get_patent_numbers(modified_opinion)

        modified_opinion = regex(
            modified_opinion, self.patent_number_patterns_2, flags=re.I
        )

        # Regex to capture claim numbers followed by a patent number.
        claims_1 = re.finditer(self.claim_patterns_1, modified_opinion, flags=re.I)

        claim_numbers = {}
        for c in claims_1:
            new_key = c.group(2)
            new_value = regex(
                c.group(1),
                [
                    (r" ?through ?", "-"),
                    (r"(\d+)[\- ]+(\d+)", r"\g<1>-\g<2>"),
                    (r"[^0-9\-]+", " "),
                    *self.strip_patterns,
                    *self.space_patterns,
                ],
            )
            if claim_numbers.get(new_key, None):
                cls = claim_numbers[new_key]
                if new_value not in cls:
                    cls += [new_value]
            else:
                claim_numbers[new_key] = [new_value]

            # Remove claim numbers of the type `claims # of the '# patent` to avoid double count.
            start, end = c.span(1)
            modified_opinion = (
                modified_opinion[:start]
                + "".join(["X"] * (end - start))
                + modified_opinion[end:]
            )

        patent_refs = re.finditer(self.patent_reference_patterns, modified_opinion)

        # Regex to capture claim numbers at large or NOT followed by a patent number.
        claims_2 = re.finditer(self.claim_patterns_2, modified_opinion)

        ref_location = [
            (match.start(), match.group()) for match in patent_refs if match
        ]

        claims = {match.start(): match.group() for match in claims_2 if match}

        if ref_location:
            for key, value in claims.items():
                new_key = regex(
                    ref_location[closest_value([ref[0] for ref in ref_location], key)][
                        1
                    ],
                    [(r"[^0-9]+", "")],
                )
                new_value = regex(
                    value,
                    [
                        (r" ?through ?", "-"),
                        (r"(\d+)[\- ]+(\d+)", r"\g<1>-\g<2>"),
                        (r"[^0-9\-]+", " "),
                        *self.strip_patterns,
                        *self.space_patterns,
                    ],
                )

                if claim_numbers.get(new_key, None):
                    cls = claim_numbers[new_key]
                    if new_value not in cls:
                        cls += [new_value]
                else:
                    claim_numbers[new_key] = [new_value]

            # If no claim is associated with any patent reference, count those in with empty cited claims.
            for pat_ref in self.patent_refs:
                if not claim_numbers.get(pat_ref, None):
                    claim_numbers[pat_ref] = [""]

        # If there is only one patent, or a collectively referenced set of patents, take them in.
        if not ref_location:
            # If integer reference patterns are not found, look for e.g. "the Patent(s)" as an alternative.
            noninteger_refs = regex(
                modified_opinion,
                self.special_patent_ref_patterns,
                sub=False,
                flags=re.I,
            )
            if (noninteger_refs and self.patent_numbers) or len(
                self.patent_numbers
            ) == 1:
                for p in self.patent_numbers:
                    for i in range(2):
                        if p[i] and not claim_numbers.get(ref_num := p[i][-3:], None):
                            claim_numbers[ref_num] = [""]
                            self.patent_refs.add(ref_num)
                            break
                    # If noninteger reference patterns point to a single patent, stop the loop at first iteration.
                    if noninteger_refs and not noninteger_refs[0][1]:
                        break

        # Expand the range of claims e.g. 1-4 --> 1, 2, 3, 4.
        for key, value in claim_numbers.items():
            value = [hyphen_to_numbers(x).split(" ") for x in value if x]
            if value:
                claim_numbers[key] = sorted(
                    rm_repeated(reduce(concat, value, [])), key=sort_int
                )

        # If an application number and a patent from that is cited at the same time,
        # remove the application number from patent_numbers and transfer all the cited
        # claims to that patent number.
        ckeys = claim_numbers.keys()
        for p in self.patent_numbers:
            if p[0] and p[1]:
                if set([p[0][-3:], p[1][-3:]]).issubset(ckeys):
                    claim_numbers[p[0][-3:]] = list(
                        filter(
                            None,
                            rm_repeated(
                                claim_numbers[p[1][-3:]] + claim_numbers[p[0][-3:]]
                            ),
                        )
                    )
                    del claim_numbers[p[1][-3:]]

        return claim_numbers

    def _tokenize_citation(self, citation):
        """
        Tokenize court data, reporter data, docket numbers, publication date,
        and case name from a valid `citation`.
        """
        citation_dic = {"citation": citation}

        [approx_location, court, day, month, year] = [None] * 5
        if fn := regex(citation, self.approx_court_location_patterns, sub=False):
            date = regex(fn[0], self.short_month_date_patterns, sub=False)
            if date:
                date = date[0]
                [month, day, year] = [nullify(x) for x in date[1:]]
                month = self.months[month] if month else None
                approx_location = fn[0].replace(date[0], year)

        if approx_location:
            if regex(approx_location, [(r"^\((?: +)?\d+(?: +)?\)$", "")], sub=False):
                court = None

            for c in self.court_codes:
                if c in approx_location:
                    court = self.jurisdictions["court_details"][c]
                    break

        total_matches = []
        # Remove reporters without a known volume or number such as ___ U.S. ___
        for key in self.reporters:
            if key in citation:
                citation = regex(
                    citation,
                    [
                        (
                            re.escape(key).join(
                                self.reporter_empty_patterns.split("X")
                            ),
                            " ",
                        )
                    ],
                )

        citation_dic["citation"] = citation = regex(
            citation, [(r"[\-—–_ ]{2,}[, ]+", " ")]
        )

        for key in self.reporters:
            if key in citation:
                matches = regex(
                    citation,
                    [(re.escape(key).join(self.reporter_patterns.split("X")), "")],
                    sub=False,
                )

                for match in matches:
                    citation = citation.replace(match[0], "XXXX")

                total_matches += matches

        citation_details = []

        keys = ["volume", "reporter_abbreviation", "first_page", "pages", "footnotes"]
        for m in total_matches:
            match = [
                self.reporters[s] if i == 1 else s
                for i, s in enumerate(
                    list(map(lambda i: regex(i, self.comma_space_patterns), m[1:]))
                )
            ]
            details = {
                k: nullify(
                    regex(match[i], [(r"[^0-9\-, ]", ""), *self.extra_char_patterns])
                )
                if i > 2
                else nullify(regex(match[i], [(r"^[_-]+$", "")]))
                for i, k in enumerate(keys)
            }

            if details["reporter_abbreviation"] == "P. C.":
                court = None

            if details["reporter_abbreviation"] in ["S. Ct.", "U.S."]:
                court = self.jurisdictions["court_details"]["Supreme Court"]

            details["edition"] = EDITIONS[details["reporter_abbreviation"]]
            reporter = REPORTERS[details["edition"]][0]
            details["reporter_name"] = reporter["name"]
            details["cite_type"] = reporter["cite_type"]

            citation_details += [details]

        def _extract_casename(citation):
            return regex(citation, [(r"^(.*?)XXXX+.*", r"\g<1>")])

        possible_casename = _extract_casename(
            regex(citation, [(self.docket_clean_patterns, r" \g<1> ")], flags=re.I)
        )

        docket_numbers = []
        while True:
            match = []
            for x in [self.docket_number_patterns, self.docket_number_comp_patterns]:
                match = regex(
                    possible_casename,
                    x,
                    sub=False,
                    flags=re.I,
                )
                if match:
                    break

            if not match:
                break

            match = match[0]

            if "XXXX" in match[1]:
                possible_casename = possible_casename.replace(match[0], " XXXX")
                break

            else:
                docket_numbers += regex(match[1], [(r",? +and +", ",")]).split(",")

                if not regex(
                    possible_casename.replace(match[1], ","),
                    self.docket_number_patterns,
                    sub=False,
                    flags=re.I,
                ):
                    possible_casename = possible_casename.replace(match[0], " XXXX")
                    break

                else:
                    possible_casename = possible_casename.replace(match[1], ",")

        casename = nullify(
            regex(
                _extract_casename(possible_casename),
                self.comma_space_patterns,
            )
        )

        citation_dic["case_name"] = None if casename == citation else casename
        citation_dic["published"] = False if docket_numbers else True
        citation_dic["date"] = {"year": year, "month": month, "day": day}
        citation_dic["docket_numbers"] = nullify(
            regex(
                docket_numbers,
                [(self.docket_clean_patterns, r""), *self.comma_space_patterns],
                flags=re.I,
            )
        )
        citation_dic["citation_details"] = nullify(citation_details)
        citation_dic["court"] = court
        return citation_dic

    def _get_patent_numbers(self, opinion):
        """
        Get the patent numbers cited in the court case. If there is any application number
        cited, grab the patent number, if any, and return the pair. If there is no application
        number, return 'None' together with the patent number.
        """
        patent_numbers = rm_repeated(
            [
                y
                for y in map(
                    lambda x: (regex(x, [(r"(?!/)\W", "")]), None),
                    regex(
                        opinion, self.patent_number_patterns_1, sub=False, flags=re.I
                    ),
                )
                if y[0] != "US"
            ]
        )

        # Make sure that patterns like `'#number patent or patent '#number` are there to sift through
        # extracted patent numbers and keep the ones cited later in the case text.
        self.patent_refs = set(
            filter(
                None,
                reduce(
                    concat,
                    [
                        i
                        for i in regex(
                            opinion,
                            [(self.patent_reference_patterns, "")],
                            sub=False,
                        )
                    ],
                    (),
                ),
            )
        )

        if len(patent_numbers) > 1:
            patent_numbers = [
                [p for p in self._patent_from_application(x[0])] for x in patent_numbers
            ]

        elif len(patent_numbers) == 1 or (
            not self.patent_refs
            and regex(opinion, [(r"[pP]atents-in-[sS]uit", "")], sub=False)
        ):
            patent_numbers = [
                [p for p in self._patent_from_application(x[0])] for x in patent_numbers
            ]

        self.patent_numbers = reduce(concat, patent_numbers, [])
        return

    def _patents_in_suit(self, skip_patent):
        """
        Collect and store all relevant patents in suit including the text of all claims
        with the claims cited in the text of a gcl file identified.
        """
        patents = []
        for key, value in self._get_claim_numbers().items():
            for p in self.patent_numbers:
                patent_number, appl_number = p
                if (patent_number and patent_number.endswith(key)) or (
                    appl_number and appl_number.endswith(key)
                ):
                    patent_found, claims = False, {}
                    if patent_number:
                        patent_found, claims = self.gcl_patent_data(
                            patent_number, self.case["id"], skip_patent, True
                        )
                    extra = []
                    mixed_claim_numbers = set(claims.keys()) if claims else set()
                    if uc := self._updated_claims(appl_number):
                        extra = uc
                        mixed_claim_numbers |= set(uc[0]["updated_claims"].keys())

                    # Only append a patent if it has nonempty claimset.
                    if claims:
                        patents.append(
                            {
                                "patent_number": patent_number or None,
                                "application_number": appl_number or None,
                                "patent_found": patent_found,
                                "claims": claims,
                                "extra": extra,
                                "cited_claims": [
                                    int(i)
                                    for i in value
                                    if regex(i, self.just_number_patterns, sub=False)
                                    and i in set(map(str, mixed_claim_numbers))
                                ],
                            }
                        )
                        break

        self.case["patents_in_suit"] = patents
        return

    def _updated_claims(self, appl_number):
        updated_claims = []
        if appl_number:
            xml = self.uspto.grab_ifw(
                appl_number,
                doc_codes=["CLM"],
                mime_types=["XML"],
                close_to_date=self.case["date"],
            )
            if xml:
                updated_claims += [self.uspto.parse_clm(xml[0])]
        return updated_claims

    def _is_cited(self, number):
        """
        Check if a patent or application `number` is cited repeatedly in the case
        to be considered as a legit patent under discussion.
        """
        if number[-3:] in self.patent_refs or number[-4:] in self.patent_refs:
            return True

        return False

    def _patent_from_application(self, number):
        """
        Grab the patent number (str) given an application `number` (str) from
        https://patentcenter.uspto.gov/ and return the pair. If no patent number
        is found, return the application number. If `number` is a valid
        patent number, then yield the patent number.

        Example
        -------
        >>> list(_patent_from_application('11/685,188'))
        [('US7631336', 11685188)]

        >>> list(_patent_from_application('4,566,345'))
        [('US4566345', None)]

        """
        standard_number = regex(number, self.standard_patent_patterns)

        if "/" in number:
            metadata = self.uspto.peds_call(searchText=f"applId:({standard_number})")
            response = metadata["queryResults"]["searchResponse"]["response"]
            if response["numFound"] > 0:
                docs = response["docs"][0]
                appl_data = docs.get("childContinuity", []) or docs.get(
                    "appEarlyPubNumber", ""
                )
                if isinstance(appl_data, list):
                    for ap in appl_data:
                        for pnum in ["patentNumberText", "applicationNumberText"]:
                            if kn := ap.get(pnum, None):
                                if self._is_cited(kn):
                                    country = (
                                        docs.get("corrAddrCountryCd", None) or "US"
                                    )
                                    if pnum == "applicationNumberText":
                                        kn = ap["patentNumberText"]
                                        if not kn:
                                            country = ""
                                    yield f"{country}{kn}", standard_number
                                else:
                                    yield None, standard_number
                else:
                    kn = regex(appl_data, self.standard_patent_patterns)
                    if self._is_cited(kn):
                        yield f"US{kn}", standard_number
                    else:
                        yield None, standard_number
            else:
                yield None, standard_number
        else:
            yield f"US{standard_number}", None

    def _serialize_footnotes(self):
        """
        Serialize the footnotes and remove their associated tags from the end of case file.
        """
        if small_tag := self.opinion.find_all("small"):
            self._replace_i_tags(small_tag[-1])
            footnotes = small_tag[-1].find_all("a", class_="gsl_hash")
            for tag in footnotes:
                parent_tag = tag.parent
                tag.replaceWith("")
                self.case["footnotes"].append(
                    {
                        "identifier": f"{tag.attrs['name']}",
                        "context": regex(parent_tag.get_text(), self.space_patterns),
                    }
                )

        self._prioritize_citations = None
        return

    def _replace_generic_tags(self):
        """
        Remove or replace all the tags at large with their appropriate labels.
        """
        court_code = self.case["court"].get("court_code", None)

        for el in self.opinion.find_all("center"):
            el.replaceWith("")

        for h in self.opinion.find_all("h2"):
            if court_code in ["us"]:
                if "Syllabus" not in h.get_text():
                    h.replaceWith("")
            else:
                h.replaceWith("")

        for p in self.opinion.find_all("a", class_="gsl_pagenum"):
            p.replaceWith(f" +page[{p.get_text()}]+ ")

        for a in self.opinion.find_all("a", class_="gsl_pagenum2"):
            a.replaceWith("")

        self._replace_i_tags(self.opinion)

        for bq in self.opinion.find_all("blockquote"):
            text = bq.get_text()
            if text:
                bq.replaceWith(
                    f" {self.blockquote_label_s} {text} {self.blockquote_label_e} "
                )

        for pre in self.opinion.find_all("pre"):
            text = pre.get_text()
            if text:
                pre.replaceWith(f" {self.pre_label_s} {text} {self.pre_label_e} ")

        # Locate tag with judge names and remove it along with every <p></p> coming before this tag.
        # Meant to clean up the text by removing the party names.
        judge_tag = self.gcl_get_judge(just_locate=True)
        end_replace = False
        # Remove everything in the non-Supreme Court cases up to the paragraph with judge information.
        if judge_tag and court_code not in ["us"]:
            for p in self.opinion.find_all("p"):
                if not end_replace:
                    if p == judge_tag and judge_tag not in p.find_all("p"):
                        end_replace = True
                    if judge_tag not in p.find_all("p"):
                        p.replaceWith("")
                else:
                    break

        # Remove everything before Syllabus for Supreme Court cases.
        if court_code in ["us"]:
            for h in self.opinion.find_all(lambda tag: tag.name in ["p", "h2"]):
                if not end_replace:
                    if h.name == "h2":
                        if "Syllabus" in h.get_text():
                            end_replace = True
                        h.replaceWith("")
                    else:
                        if judge_tag:
                            if h == judge_tag and judge_tag not in h.find_all("p"):
                                end_replace = True
                            if judge_tag not in h.find_all("p"):
                                h.replaceWith("")
                else:
                    break

        for p in self.opinion.find_all("p"):
            text = p.get_text()
            if not text:
                p.replaceWith("")
            else:
                if regex(text, self.end_sentence_patterns, sub=False):
                    p.replaceWith(f"{text} {self.paragraph_label} ")
                else:
                    p.replaceWith(text)

        small = self.opinion.find_all("small")
        if small:
            small[-1].replaceWith("")

        return

    def _training_text(self):
        """
        Create the final labeled text of the opinion for training purposes.
        """
        self.case["training_text"] = regex(self.opinion.get_text(), self.strip_patterns)
        return

    def _personal_opinion(self):
        """
        Determine if a case from Circuit Courts involves personal opinion of a judge(s)
        e.g. "dissent" or "concur". Return a dictionary including the name of every judge
        hearing the case, together with a sub-key "index_span" that shows the range of positional
        indices of the personal opinion located in `training_text`.
        """
        training_text, judges = self.case["training_text"], self.case["judges"]
        opinion_tags = list(
            re.finditer(self.judge_dissent_concur_patterns, training_text)
        )
        opinion_dict, indices = {"concur": None, "dissent": None}, {}

        for i, tag in enumerate(opinion_tags):
            indices[i] = tag.start()

        for judge in judges:
            for i, tag in enumerate(opinion_tags):
                if judge.lower() in tag.group(1).lower():
                    op_type = filter(
                        lambda x: x in tag.group(0).lower(),
                        ["concurring", "dissenting"],
                    )
                    for o in op_type:
                        dc = regex(o, [(r"r?ing$", "")])

                        if opinion_dict[dc] is None:
                            opinion_dict[dc] = []

                        # Fix the end index of each tuple in `index_span` by replacing it with
                        # the start index of the next index, if any. Otherwise,
                        # replace the end index with the length of `training_text`.
                        end_index = len(training_text)
                        if i < len(opinion_tags) - 1:
                            end_index = indices[i + 1]

                        opinion_dict[dc] += [
                            {"judge": judge, "index_span": (tag.start(), end_index)}
                        ]
        self.case["personal_opinions"] = opinion_dict
        return
