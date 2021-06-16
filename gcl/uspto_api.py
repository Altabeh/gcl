"""
This module provides a python wrapper for USPTO APIs.

The offered features include downloading, parsing and serializing
PTAB data, bulk search and download of applications and patents,
PEDS, transaction history, IFW and etc.
"""

import json
import random
import re
from copy import deepcopy
from datetime import datetime
from functools import reduce
from logging import getLogger
from operator import concat
from os import path
from pathlib import Path
from time import sleep
from typing import Union
from zipfile import ZipFile

import requests
from bs4 import BeautifulSoup as BS
from dateutil import parser
from tqdm import tqdm

from gcl import __version__
from gcl.regexes import GeneralRegex, PTABRegex
from gcl.settings import root_dir
from gcl.utils import (closest_value, create_dir, deaccent, load_json, regex,
                       rm_repeated, timestamp)

logger = getLogger(__name__)


class USPTOscrape(PTABRegex, GeneralRegex):
    """
    A class that uses USPTO APIs to download and parse useful data for the gcl class.
    """

    __uspto_dev_base_url__ = "https://developer.uspto.gov/"
    __headers__ = {"Content-Type": "application/json", "Accept": "application/json"}
    __query_params__ = {}

    def __init__(self, **kwargs):
        self.data_dir = create_dir(kwargs.get("data_dir", root_dir / "gcl" / "data"))
        self.suffix = kwargs.get("suffix", f"v{__version__}")

    def ptab_call(self, **kwargs):
        """
        Call PTAB proceedings and documents REST API.
        """
        self.__query_params__ = {
            "dateRangeData": {},
            "facetData": {},
            "parameterData": {},
            "recordTotalQuantity": "100",
            "searchText": "",
            "sortDataBag": [],
            "recordStartNumber": 0,
        }
        for key, value in kwargs.items():
            self.__query_params__[key] = value

        r = requests.post(
            url=f"{self.__uspto_dev_base_url__}ptab-api/decisions/json",
            json=self.__query_params__,
            headers=self.__headers__,
        )

        metadata = r.json()
        record_per_call = int(self.__query_params__["recordTotalQuantity"])
        self.save_metadata(
            metadata,
            suffix=f'-{int(self.__query_params__["recordStartNumber"]/record_per_call)}',
            dir_name="ptab-api",
        )

        if kwargs.get("getAll", False):
            if e := metadata.get("error", None):
                raise Exception(f"Server returned {e}.")
            while (
                self.__query_params__["recordStartNumber"] + record_per_call
                < metadata["recordTotalQuantity"]
            ):
                logger.info(
                    f'Records left: {metadata["recordTotalQuantity"] - self.__query_params__["recordStartNumber"]}'
                )
                self.__query_params__["recordStartNumber"] += record_per_call
                self.ptab_call()
                break

    def bulk_search_download_call(
        self, start: int = 0, rows: int = 100, **kwargs
    ) -> None:
        """
        Call bulk search and download API.
        """

        url = f"https://developer.uspto.gov/ibd-api/v1/patent/application?start={start}&rows={rows}"

        if kwargs:
            for key, val in kwargs.items():
                url += f"&{key}={val}"

        r = requests.get(url=url, headers=self.__headers__)
        metadata = r.json()["response"]
        self.save_metadata(
            metadata,
            suffix=f"-{int(start/rows)}",
            filename="docs",
            dir_name="bulk-search-api",
        )
        if kwargs.get("getAll", False):
            if e := metadata.get("error", None):
                raise Exception(f"Server returned {e}.")

            while start + rows < metadata["numFound"]:
                logger.info(f'Records left: {metadata["numFound"] - start}')
                start += rows
                self.bulk_search_download_call(start=start, rows=rows, **kwargs)
                break
        return

    def save_metadata(
        self,
        metadata: dict,
        suffix: str = "",
        filename: str = "response",
        dir_name: str = "meta",
    ) -> None:
        """
        Save metadata files downloaded using any method that calls a USPTO API.

        Args
        ----
        * :param file_name: ---> str: name of the metadata file to save.
        """
        json_subdir = f"json_{self.suffix}"
        for value in metadata.values():
            json_path = (
                create_dir(self.data_dir / "uspto" / dir_name / json_subdir)
                / f"{filename}{suffix}.json"
            )
            with open(json_path.__str__(), "w") as f:
                json.dump(value, f, indent=4)
        return

    def ptab_document_download_api(self, metadata: dict, pause: bool = False) -> None:
        """
        Download PTAB documents whose metadata are stored in a `metadata` file
        by calling PTAB Documents REST API.

        Args
        ----
        * :param pause: ---> bool: allows a 1-second pause before making a new call
        to download a document to avoid getting blocked by the server.
        """
        doc_subdir = f"doc_{self.suffix}"
        doc_path = (
            create_dir(self.data_dir / "uspto" / "ptab-api" / doc_subdir)
            / metadata["documentName"]
        )
        if not doc_path.is_file():
            if pause:
                sleep(1)
            r = requests.get(
                url=f'{self.__uspto_dev_base_url__}ptab-api/documents/{metadata["documentIdentifier"]}/download'
            )

            with open(doc_path.__str__(), "wb") as f:
                f.write(r.content)
            logger.info(f'{metadata["documentName"]} saved successfully')

        logger.info(f'{metadata["documentName"]} already saved')
        return

    def aggrigator(
        self, special_keys: list = None, map_key: str = None, drop_keys: list = None
    ) -> list:
        """
        Generate a serialized version of the uspto metadata files.
        Use `map_key` to map all metadata to a single key for faster querying.

        Args
        ----
        * :param special_keys: ---> list: a special list of keys to be aggrigated and serialized.
        * :param map_key: ---> str: a key from the metadata files to create a
        dictionary of the form {key: metadata}.
        * :param drop_keys: ---> list: a list of key(s) to drop from metadata files.
        """
        json_subdir = f"json_{self.suffix}"
        json_dir = self.data_dir / "uspto" / "meta" / json_subdir
        metadata_files = [
            x for x in json_dir.glob("*.json") if not x.name.startswith("aggregated")
        ]
        metadata_files.sort(key=path.getmtime)

        logger.info(
            f"Starting metadata aggrigation of json files under directory {json_dir.__str__()} ..."
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
            str(create_dir(json_dir / "aggregated") / f"aggregated_{self.suffix}.json"),
            "w",
        ) as f:
            json.dump({"aggregated_data": total}, f, indent=4)

        return total

    def grab_ifw(
        self,
        appl_number: str,
        doc_codes: list = None,
        mime_types: list = None,
        close_to_date: str = None,
        skip_download: bool = False,
    ) -> list:
        """
        Download image file wrapper for a given application number `appl_number`.

        Args
        ----
        * :param doc_codes: ---> list: contains specific document codes to be downloaded.
        * :param mime_types: ---> list: contains specific file mime types to be downloaded.
        * :param close_to_date: ---> str: allows to restrict the downloading of files to those
        * with official dates closest to this date.
        * :param skip_download: ---> bool: if true, skips downloading data files whose metadata are stored in
        the transactions.
        """

        appl_number = regex(appl_number, self.special_chars_patterns)
        pc_base_url = "https://patentcenter.uspto.gov/retrieval/public"
        meta_url = f"{pc_base_url}/v1/applications/sdwp/external/metadata/{appl_number}"
        post_url = f"{pc_base_url}/v2/documents/"

        transactions_folder = create_dir(
            self.data_dir
            / "uspto"
            / "ifw"
            / f"transactions_{self.suffix}"
            / appl_number
        )

        errorBag = []

        if (fn := transactions_folder / f"transactions_{appl_number}.json").is_file():
            transactions = load_json(fn)

        else:
            while True:
                sleep(1)
                transactions = {}
                r = requests.get(meta_url, headers=self.__headers__)
                try:
                    transactions = r.json()
                    if retry := r.headers.get("Retry-After", None):
                        logger.info(
                            f"Accessing {meta_url} is blocked for {retry} seconds"
                        )
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

            # Make the costumer numbers random to reduce retry chances.
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
                                "customerNumber": cs_num,
                                "mailDateTime": official_date,
                                "documentCode": doc["documentCode"],
                                "mimeCategory": mime,
                                "previewFileIndicator": False,
                                "documentCategory": doc["directionCategory"],
                            }
                        ]
                        documentInformationBag += doc_bag

                headers, json_data = deepcopy(self.__headers__), {}
                for bag in documentInformationBag:
                    json_data = {
                        "fileTitleText": doc["documentIdentifier"],
                        "documentInformationBag": [bag],
                    }
                    if skip_download:
                        logger.info(
                            f"The document with the ID `{bag['documentIdentifier']}` has not been downloaded. Please set `skip_download=False` and try again."
                        )
                    else:
                        headers["Accept"] = f"application/{bag['mimeCategory']}"
                        while True:
                            r = requests.post(post_url, json=json_data, headers=headers)
                            if retry := r.headers.get("Retry-After", None):
                                logger.info(
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
                            logger.info(
                                f"{filename} was downloaded and saved successfully"
                            )

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

    def parse_clm(self, xml_file: Union[Path, str]) -> dict:
        """
        Parse the xml file for the claims, i.e. items having the code "CLM"
        in the transaction history between applicant and the USPTO office .
        """
        if not isinstance(xml_file, Path):
            xml_file = Path(xml_file)

        clm = BS(deaccent(xml_file.read_text()), "lxml")
        date = clm.find(self.official_mailroom_date_patterns).get_text()

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
            else:
                claim_number = int(claim_number)

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
            cited_claims = None
            if fn := regex(
                context,
                self.dependent_claim_patterns,
                sub=False,
                flags=re.I,
            ):
                gn = fn[0]

                if gn[0]:
                    if gn[1]:
                        if gn[2] and regex(gn[1], [(r"to|through|\-", "")]):
                            cited_claims = [
                                i for i in range(int(gn[0]), int(gn[2]) + 1)
                            ]
                        elif gn[2] and regex(gn[1], [(r"or|and", "")]):
                            cited_claims = [int(gn[0]), int(gn[2])]

                    else:
                        cited_claims = [int(gn[0])]

                else:
                    if gn[3] and gn[4]:
                        cited_claims = [i + 1 for i in range(claim_number - 1)]

                    elif gn[3] and not gn[4]:
                        cited_claims = [claim_number - 1]

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
                "claim_number": claim_number,
                "context": context,
                "status": status,
                "dependent_on": cited_claims,
            }

            claims_data["updated_claims"][claim_number] = data
            if not context and status == "original":
                del claims_data["updated_claims"][claim_number]

        if not claims_data["updated_claims"]:
            return {}

        return claims_data

    def peds_call(self, **kwargs) -> dict:
        """
        Call the PEDS API.
        """
        url = "https://ped.uspto.gov/api/queries"

        self.__query_params__ = {
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
            self.__query_params__[key] = value

        while True:
            sleep(1)
            metadata = {}
            r = requests.post(
                url=url,
                json=self.__query_params__,
                headers=self.__headers__,
            )
            try:
                metadata = r.json()
                if retry := r.headers.get("Retry-After", None):
                    logger.info(f"Accessing {url} is blocked for {retry} seconds")
                    sleep(int(retry))
                else:
                    break
            except ValueError or json.decoder.JSONDecodeError:
                pass

        return metadata
