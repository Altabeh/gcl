"""
This module provides a python wrapper for USPTO APIs.

The offered features include downloading, parsing and serializing
PTAB data, bulk search and download of applications and patents,
PEDS, transaction history, IFW and etc.
"""

import json
import random
import re
import sys
from copy import deepcopy
from datetime import datetime
from functools import reduce
from operator import concat
from os import path
from pathlib import Path
from time import sleep
from zipfile import ZipFile

import requests
from bs4 import BeautifulSoup as BS
from dateutil import parser
from tqdm import tqdm

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, BASE_DIR.__str__())

from utils import (closest_value, create_dir, deaccent, get, regex,
                   rm_repeated, timestamp, validate_url)

from regexes import GeneralRegex, PTABRegex


class USPTOscrape(PTABRegex, GeneralRegex):

    base_url = "https://developer.uspto.gov/"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    today = datetime.date(datetime.now()).strftime("%Y-%m-%d")

    query_params = {}

    def __init__(self, **kwargs):
        # Default relative url will be `ptab-api/decisions/json` but it can be adjusted to
        # any other API offered by USPTO.
        self.relative_url = kwargs.get("relative_url", "ptab-api/decisions/json")
        self.data_dir = create_dir(
            kwargs.get(
                "data_dir",
                BASE_DIR / "gcl" / "uspto-data" / self.relative_url.split("/")[0],
            )
        )
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)
        self.suffix = kwargs.get("suffix", "v1")

    def ptab_call(self, **kwargs):
        """
        Call PTAB proceedings and documents REST API.
        """
        self.query_params = {
            "dateRangeData": {},
            "facetData": {},
            "parameterData": {},
            "recordTotalQuantity": "100",
            "searchText": "",
            "sortDataBag": [],
            "recordStartNumber": 0,
        }
        for key, value in kwargs.items():
            self.query_params[key] = value

        r = requests.post(
            url=self.base_url + self.relative_url,
            json=self.query_params,
            headers=self.headers,
        )

        metadata = r.json()
        record_per_call = int(self.query_params["recordTotalQuantity"])
        self.save_metadata(
            metadata,
            suffix=f'-{int(self.query_params["recordStartNumber"]/record_per_call)}',
        )

        if kwargs.get("getAll", False):
            if e := metadata.get("error", None):
                raise Exception(f"Server returned {e}.")
            while (
                self.query_params["recordStartNumber"] + record_per_call
                < metadata["recordTotalQuantity"]
            ):
                print(
                    f'Records left: {metadata["recordTotalQuantity"] - self.query_params["recordStartNumber"]}'
                )
                self.query_params["recordStartNumber"] += record_per_call
                self.ptab_call()
                break

    def bulk_search_download_call(self, start=0, rows=100, **kwargs):
        """
        Call bulk search and download API.
        """

        url = f"https://developer.uspto.gov/ibd-api/v1/patent/application?start={start}&rows={rows}"

        if kwargs:
            for key, val in kwargs.items():
                url += f"&{key}={val}"

        r = requests.get(url=url, headers=self.headers)
        metadata = r.json()["response"]
        self.save_metadata(metadata, suffix=f"-{int(start/rows)}", filename="docs")
        if kwargs.get("getAll", False):
            if e := metadata.get("error", None):
                raise Exception(f"Server returned {e}.")

            while start + rows < metadata["numFound"]:
                print(f'Records left: {metadata["numFound"] - start}')
                start += rows
                self.bulk_search_download_call(start=start, rows=rows, **kwargs)
                break

    def save_metadata(self, metadata, suffix="", filename="response"):
        """
        Save metadata files downloaded using any method that calls a USPTO API.

        Args
        ----
        :param file_name: ---> str: name of the metadata file to save.
        """
        json_subdir = f"json_{self.suffix}"
        for value in metadata.values():
            json_path = (
                create_dir(self.data_dir / json_subdir) / f"{filename}{suffix}.json"
            )
            with open(json_path.__str__(), "w") as f:
                json.dump(value, f, indent=4)

    def download_api(self, metadata, pause=False):
        """
        Download documents whose metadata are stored in a `metadata` file.

        Args
        ----
        :param pause: ---> bool: allows a 1-second pause before making a new call
        to download a document to avoid getting blocked by the server.
        """
        doc_subdir = f"doc_{self.suffix}"
        doc_path = create_dir(self.data_dir / doc_subdir) / metadata["documentName"]
        if not doc_path.is_file():
            url = (
                self.base_url
                + self.relative_url.split("/")[0]
                + f'/documents/{metadata["documentIdentifier"]}/download'
            )
            if pause:
                sleep(1)
            r = requests.get(url=url)

            with open(doc_path.__str__(), "wb") as f:
                f.write(r.content)
            print(f'{metadata["documentName"]} saved successfully')

        print(f'{metadata["documentName"]} already saved')

    def aggrigator(self, special_keys=None, map_key=None, drop_keys=None):
        """
        Generate a serialized version of the uspto metadata files.
        Use `map_key` to map all metadata to a single key for faster querying.

        Args
        ----
        :param special_keys: ---> list: a special list of keys to be aggrigated and serialized.
        :param map_key: ---> str: a key from the metadata files to create a dictionary of the form {key: metadata}.
        :param drop_keys: ---> list: a list of key(s) to drop from metadata files.
        """
        json_subdir = f"json_{self.suffix}"
        metadata_files = [
            x
            for x in (self.data_dir / json_subdir).glob("*.json")
            if not x.name.startswith("aggregated")
        ]
        metadata_files.sort(key=path.getmtime)

        print(
            f"Starting metadata aggrigation of json files under directory {(self.data_dir / json_subdir).__str__()} ..."
        )

        total = []
        if map_key:
            total = {}

        for met in tqdm(metadata_files, total=len(metadata_files)):
            meta = []
            with open(met, "r") as f:
                meta = json.load(f)

            if map_key:
                for r in meta:
                    if drop_keys:
                        for k in drop_keys:
                            r.pop(k, None)
                    total[r[map_key]] = r

            else:
                if special_keys:
                    total += [
                        {key: r.get(key, None) for key in special_keys} for r in meta
                    ]

                else:
                    total += [
                        {
                            "documentIdentifier": r["documentIdentifier"],
                            "documentName": r["documentName"],
                        }
                        for r in meta
                    ]

        with open(
            str(
                create_dir(self.data_dir / json_subdir / "aggregated")
                / f"aggregated_{self.suffix}.json"
            ),
            "w",
        ) as f:
            json.dump({"aggregated_data": total}, f, indent=4)

        return total

    def grab_ifw(
        self, appl_number: str, doc_codes=None, close_to_date=None, mime_types=None
    ):
        """
        Download image file wrapper for a given application number `appl_number`.

        Args
        ----
        :param doc_codes: ---> list: contains specific document codes to be downloaded.
        :param close_to_date: ---> str: allows to restrict the downloading of files to those
        with official dates closest to this date.
        :param mime_types: ---> list: contains specific file mime types to be downloaded.
        """

        appl_number = regex(appl_number, self.special_chars_patterns)
        base_url = "https://patentcenter.uspto.gov/retrieval/public"
        meta_url = f"{base_url}/v1/applications/sdwp/external/metadata/{appl_number}"
        post_url = f"{base_url}/v2/documents/"

        transactions_folder = create_dir(
            self.data_dir / f"transactions_{self.suffix}" / appl_number
        )

        errorBag = []

        if (fn := transactions_folder / f"transactions_{appl_number}.json").is_file():
            transactions = self.load_external(fn.__str__())

        else:
            while True:
                sleep(1)
                transactions = {}
                r = requests.get(meta_url, headers=self.headers)
                try:
                    transactions = r.json()
                    if retry := r.headers.get("Retry-After", None):
                        print(f"Accessing {meta_url} is blocked for {retry} seconds")
                        sleep(int(retry))
                    else:
                        if r.status_code == 401:
                            errorBag = 401
                            break

                        if r.status_code == 200:
                            with open(
                                str(transactions_folder / f"{appl_number}.json"), "w"
                            ) as f:
                                json.dump(transactions, f, indent=4)
                            errorBag = transactions["errorBag"]
                            break

                except ValueError or json.decoder.JSONDecodeError:
                    pass

        if not errorBag:
            documents = transactions["resultBag"][0]["documentBag"]

            # Apply filter to only download specific document codes and mime types.
            docs = []
            for i, n in enumerate([doc_codes, mime_types]):
                if n:
                    if not isinstance(n, list):
                        raise Exception(f"{n} must be a list")

                    if not i:
                        documents = list(
                            filter(lambda doc: doc["documentCode"] in n, documents)
                        )
                    else:
                        for doc in documents:
                            if fn := list(set(doc["mimeTypeBag"]) & set(n)):
                                doc["mimeTypeBag"] = fn
                                docs += [doc]
            if mime_types:
                documents = docs

            # Apply filter to only download a specific document with the official date closest to `close_to_date`.
            if close_to_date:
                if not isinstance(close_to_date, str):
                    raise Exception("`close_to_date` must be a string")

                if documents:
                    try:
                        documents = [
                            documents[
                                closest_value(
                                    [
                                        int(timestamp(doc["officialDate"]))
                                        for doc in documents
                                    ],
                                    int(timestamp(close_to_date)),
                                    none_allowed=False,
                                )
                            ]
                        ]
                    except TypeError:
                        documents = []

            documentInformationBag = []

            cs_num = str(random.randint(1, 1000000))
            for doc in documents:
                mail_date = (
                    parser.parse(doc["officialDate"]).strftime("%Y-%m-%d").split(" ")[0]
                )
                official_date = datetime.strftime(
                    datetime.strptime(mail_date, "%Y-%m-%d"), "%m-%d-%Y"
                )

                for mime in doc["mimeTypeBag"]:
                    filestem = f"{doc['documentIdentifier']}_{appl_number}_{official_date}_{doc['documentCode']}"

                    if mime == "XML":
                        filestem = f"{appl_number}_{mail_date}_{doc['documentCode']}"

                    if not (transactions_folder / f"{filestem}.{mime}").is_file():
                        doc_bag = [
                            {
                                "bookmarkTitleText": doc["documentDescription"],
                                "documentIdentifier": doc["documentIdentifier"],
                                "applicationNumberText": appl_number,
                                # Make the costumer numbers random to reduce retry chances.
                                "customerNumber": cs_num,
                                "mailDateTime": official_date,
                                "documentCode": doc["documentCode"],
                                "mimeCategory": mime,
                                "previewFileIndicator": False,
                                "documentCategory": doc["directionCategory"],
                            }
                        ]
                        documentInformationBag += doc_bag

                headers = deepcopy(self.headers)

                json_data = {}
                for bag in documentInformationBag:
                    json_data = {
                        "fileTitleText": doc["documentIdentifier"],
                        "documentInformationBag": [bag],
                    }
                    headers["Accept"] = f"application/{bag['mimeCategory']}"
                    while True:
                        r = requests.post(post_url, json=json_data, headers=headers)
                        if retry := r.headers.get("Retry-After", None):
                            print(
                                f"Accessing {post_url} is blocked for {retry} seconds"
                            )
                            sleep(int(retry))
                        else:
                            break

                    filename = regex(
                        r.headers["Content-Disposition"],
                        [
                            (
                                r".*filename=\d+_",
                                f"{doc['documentIdentifier']}_",
                            )
                        ],
                    )

                    file_path = transactions_folder / filename
                    with open(file_path.__str__(), "wb") as f:
                        f.write(r.content)
                        print(f"{filename} was downloaded and saved successfully")

                    if file_path.suffix.lower() in [".zip"]:
                        with ZipFile(file_path.__str__(), "r") as zipf:
                            zipf.extractall(transactions_folder.__str__())
                        file_path.unlink()

                    sleep(1)

            paths = []
            for f in transactions_folder.iterdir():
                if f.is_file():
                    cs_num_removed_path = transactions_folder / regex(
                        f.name, [(r"^" + re.escape(cs_num) + "_", "")]
                    )
                    f.rename(cs_num_removed_path)
                    if mime_types:
                        if f.suffix.lower() in [f".{m.lower()}" for m in mime_types]:
                            paths.append(cs_num_removed_path)
                    else:
                        paths.append(cs_num_removed_path)

            return rm_repeated(paths)

    def parse_clm(self, xml_file):
        """
        Parse the xml file for the claims, i.e. items having the code "CLM"
        in the transaction history between applicant and the USPTO office .
        """
        if not isinstance(xml_file, Path):
            xml_file = Path(xml_file)

        clm = BS(deaccent(xml_file.read_text()), "lxml")
        date = clm.find(self.date_patterns).get_text()

        if cs := clm.find(self.claimset_tag_patterns):
            clm = cs

        claims = clm.find_all(
            lambda tag: regex(tag.name, self.claim_tag_patterns, sub=False)
            and reduce(
                concat,
                regex(
                    [
                        tag.attrs.get(t, None)
                        for t in self.id_tag_patterns
                        if tag.attrs.get(t, None)
                    ],
                    [(r"^CLM", "")],
                    sub=False,
                ),
                [],
            )
        )
        claims_data = {"date": date, "updated_claims": {}}
        for cl in claims:
            claim_number = cl.attrs.get("num", None)
            if not claim_number:
                if cnum := cl.find(self.claim_num_patterns):
                    claim_number = int(cnum.get_text())

            context = BS(
                "\n".join([str(c) for c in cl.find_all(self.claim_text_patterns)]),
                "html.parser",
            )
            list(
                map(
                    lambda x: [
                        c.replaceWith("") for c in context.find_all(re.compile(x))
                    ],
                    self.unnecessary_patterns,
                )
            )
            context = regex(
                context.get_text(), [*self.space_patterns, (r"^(?:(?:[\d\.\- ])+)", "")]
            )
            dependent_on = None
            if fn := cl.find_all(self.claim_ref_patterns):
                for s in claims:
                    if gn := set(
                        filter(
                            None,
                            list(
                                map(
                                    lambda m: s.attrs.get(m, None), self.id_tag_patterns
                                )
                            ),
                        )
                    ):
                        if gn & set(
                            filter(
                                None,
                                list(
                                    map(
                                        lambda m: fn[0].attrs.get(m, None),
                                        self.id_ref_tag_patterns,
                                    )
                                ),
                            )
                        ):
                            dependent_on = int(
                                s.find(self.claim_num_patterns).get_text()
                            )
                            break
            status = re.search(r"^\(([A-Za-z ]+)\)", context)
            if status:
                context = context.replace(status.group(0), "")
                status = regex(status.group(1).lower(), [(r" ", "_")])
            else:
                status = "original"

            context = regex(context, [*self.strip_patterns, *self.space_patterns])

            if len(context) < 2:
                context = None

            data = {
                "claim_number": int(claim_number),
                "context": context,
                "status": status,
                "dependent_on": dependent_on,
            }

            claims_data["updated_claims"][claim_number] = data
            if not context and status == "original":
                del claims_data["updated_claims"][claim_number]

        if not claims_data["updated_claims"]:
            return {}

        return claims_data

    def peds_call(self, **kwargs):
        """
        Call the PEDS API.
        """
        url = "https://ped.uspto.gov/api/queries"

        self.query_params = {
            "searchText": "",
            "fq": [],
            "fl": "*",
            "mm": "0%",
            "df": "patentTitle",
            "qf": "appEarlyPubNumber applId appLocation appType appStatus_txt appConfrNumber appCustNumber appGrpArtNumber appCls appSubCls appEntityStatus_txt patentNumber patentTitle inventorName firstNamedApplicant appExamName appExamPrefrdName appAttrDockNumber appPCTNumber appIntlPubNumber wipoEarlyPubNumber pctAppType firstInventorFile appClsSubCls rankAndInventorsList",
            "facet": "true",
            "sort": "applId asc",
            "start": "0",
        }

        for key, value in kwargs.items():
            self.query_params[key] = value

        while True:
            sleep(1)
            metadata = {}
            r = requests.post(
                    url=url,
                    json=self.query_params,
                    headers=self.headers,
            )
            try:
                metadata = r.json()
                if retry := r.headers.get("Retry-After", None):
                    print(f"Accessing {url} is blocked for {retry} seconds")
                    sleep(int(retry))
                else:
                    break
            except ValueError or json.decoder.JSONDecodeError:
                pass

        return metadata

    def patent_data(self, number_or_url: str, skip_patent=False, return_data=False):
        """
        Download and scrape data for a patent with Patent (Application) No. or valid url `number_or_url`.

        Example
        -------
        >>> patent_data('https://patents.google.com/patent/US20150278825A1/en')

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

        found = False

        if not number_or_url:
            print("Please enter a valid patent number or Google Patents URL")
            return found, {}

        try:
            if validate_url(number_or_url):
                url = number_or_url
                if fn := regex(url, [(r"(?<=patent/).*?(?=/|$)", "")], sub=False):
                    patent_number = fn[0]
        except:
            patent_number = number_or_url

        json_path = (
            self.data_dir
            / f"patent_{self.suffix}"
            / patent_number
            / f"{patent_number}.json"
        )

        if json_path.is_file():
            if return_data:
                with open(json_path.__str__(), "r") as f:
                    info = json.load(f)
            found = True

        else:
            if not skip_patent:
                url = f"https://patents.google.com/patent/{patent_number}"
                status, html = get(url)
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
                        with open(json_path.__str__(), "w") as f:
                            print(f"Saving patent data for Patent No. {patent_number}...")
                            create_dir(json_path.parent)
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

    @staticmethod
    def load_external(external_file):
        """
        Load an external json file.
        """
        data = {}
        with open(external_file, "r") as f:
            data = json.load(f)
        return data
