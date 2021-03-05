import json
import random
import re
import sys
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

from tools.regexes import USPTORegex
from utils import (
    closest_value,
    create_dir,
    deaccent,
    multi_run,
    regex,
    remove_repeated,
    timestamp,
)

class USPTOscrape(USPTORegex):

    base_url = "https://developer.uspto.gov/"
    headers = {"Content-type": "application/json", "Accept": "application/json"}
    today = datetime.date(datetime.now()).strftime("%Y-%m-%d")

    query_params = {
        "dateRangeData": {},
        "facetData": {},
        "parameterData": {},
        "recordTotalQuantity": "100",
        "searchText": "",
        "sortDataBag": [],
        "recordStartNumber": 0,
    }

    def __init__(self, **kwargs):
        self.relative_url = kwargs.get("relative_url", "ptab-api/decisions/json")
        self.data_dir = create_dir(
            kwargs.get(
                "data_dir",
                BASE_DIR / "tools" / "uspto-data" / self.relative_url.split("/")[0],
            )
        )
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)
        self.suffix = kwargs.get("suffix", "v1")

    def api_call(self, **kwargs):

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
                self.query_params["recordStartNumber"] / record_per_call
                < metadata["recordTotalQuantity"] / record_per_call
            ):
                print(
                    f'Records left: {metadata["recordTotalQuantity"] - self.query_params["recordStartNumber"]}'
                )
                self.query_params["recordStartNumber"] += record_per_call
                self.api_call()

    def save_metadata(self, metadata, suffix=""):
        json_subdir = f"json_{self.suffix}"
        for key, value in metadata.items():
            if key not in ["recordTotalQuantity", "aggregationData"]:
                json_path = (
                    create_dir(self.data_dir / json_subdir) / f"{key}{suffix}.json"
                )
                with open(json_path.__str__(), "w") as f:
                    json.dump(value, f, indent=4)

    def download_api(self, metadata, pause=False):
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
        metadata_files = list((self.data_dir / json_subdir).glob("*.json"))
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
                    total += [{key: r[key] for key in special_keys} for r in meta]

                else:
                    total += [
                        {
                            "documentIdentifier": r["documentIdentifier"],
                            "documentName": r["documentName"],
                        }
                        for r in meta
                    ]

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
                response = requests.get(meta_url, headers=self.headers)
                transactions = response.json()

                try:
                    errorBag = transactions["errorBag"]
                    break

                except KeyError:
                    sleep(0.5)
                    continue

            if response.status_code == 200:
                with open(
                    str(transactions_folder / f"{appl_number}.json"),
                    "w",
                ) as f:
                    json.dump(transactions, f, indent=4)

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

                try:
                    documents = [
                        documents[
                            closest_value(
                                [
                                    int(timestamp(doc["officialDate"]))
                                    for doc in documents
                                ],
                                int(timestamp(close_to_date)),
                            )
                        ]
                    ]
                except ValueError and TypeError:
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

                headers = self.headers

                json_data = {}
                for bag in documentInformationBag:
                    json_data = {
                        "fileTitleText": doc["documentIdentifier"],
                        "documentInformationBag": [bag],
                    }
                    headers["Accept"] = f"application/{bag['mimeCategory']}"
                    r = requests.post(post_url, json=json_data, headers=headers)
                    while True:
                        retry = r.headers.get("Retry-After", None)
                        if retry:
                            sleep(int(retry))
                            r = requests.post(post_url, json=json_data, headers=headers)

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

                    if file_path.suffix.lower() in [".zip"]:
                        with ZipFile(file_path.__str__(), "r") as zipf:
                            zipf.extractall(transactions_folder.__str__())
                        file_path.unlink()

                    sleep(1)


            def _drop_costumer_number(f):
                return regex(f.name, [(r"^" + re.escape(cs_num) + "_", "")])
            
            paths = []
            for f in transactions_folder.iterdir():
                if f.is_file():
                    f.rename(
                        transactions_folder
                        / _drop_costumer_number(f)
                    )

                    if mime_types:
                        if f.suffix.lower() in [f".{m.lower()}" for m in mime_types]:
                            paths.append(f)

                    else:
                        paths.append(f)

            return remove_repeated(paths)

    def parse_clm(self, xml_file):
        """
        Parse the xml file for the claims, i.e. items having the code "CLM"
        in the transaction history between applicant and the USPTO office .
        """
        if not isinstance(xml_file, Path):
            xml_file = Path(xml_file)

        clm = BS(deaccent(xml_file.read_text()), "lxml")
        
        date = clm.find(self.date_patterns).get_text()
        
        if cs := clm.find(self.claimset_patterns[0]):
            clm = cs

        claims = clm.find_all(
            lambda tag: tag.name in self.claim_patterns
            and reduce(
                concat,
                regex(
                    [
                        tag.attrs.get(t, None)
                        for t in self.id_patterns
                        if tag.attrs.get(t, None)
                    ],
                    [(r"^CLM", "")],
                    sub=False,
                ),
            )
        )
        claims_data = {"updated_claims": {}}
        for cl in claims:
            claim_number = int(cl.find(self.claim_num_patterns).get_text())
            context = BS("\n".join([str(c) for c in cl.find_all(self.claim_text_patterns)]), "html.parser")
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
                            list(map(lambda m: s.attrs.get(m, None), self.id_patterns)),
                        )
                    ):
                        if gn & set(
                            filter(
                                None,
                                list(
                                    map(
                                        lambda m: fn[0].attrs.get(m, None),
                                        self.id_ref_patterns,
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
                "claim_number": claim_number,
                "context": context,
                "status": status,
                "dependent_on": dependent_on,
            }

            claims_data["updated_claims"][claim_number] = data
            if not context and status == "original":
                del claims_data["updated_claims"][claim_number]
        
        claims_data["date"] = date
        
        if not claims_data["updated_claims"]:
            return {}

        return claims_data

    @staticmethod
    def load_external(external_file):
        """
        Load external json file.
        """
        data = {}
        with open(external_file, "r") as f:
            data = json.load(f)
        return data


if __name__ == "__main__":
    pt = USPTOscrape(suffix="non101_v1")
    a = pt.grab_ifw(
        "10/606,729", doc_codes=["CLM"], mime_types=["XML"], close_to_date="04/08/2020"
    )
    if a:
        print(pt.parse_clm(a[0]))
    # facetData = {"proceedingTypeCategory": [{"value": "Appeal"}]}
    # pt.api_call(searchText='NOT "35 U.S.C. § 101"', facetData=facetData, getAll=True) date: 02-16-21
    # print(pt.aggrigator(map_key="documentName")["2020002933_Mail_Decision.pdf"])

    # list(
    #    multi_run(
    #        partial(pt.download_api, pause=True),
    #        pt.aggrigator()[:29000],
    #        yield_results=True,
    #    )
    # )
    # pt.download_api({"documentIdentifier": "202000095213933595Appeal2020-10-26-15:43:00", "documentName": "ali.pdf})
    xml_file = (
        BASE_DIR
        / "tools"
        / "uspto-data"
        / "ptab-api"
        / "64046_10606729_2021-02-16_CLM.xml"
    )
    # print(pt.parse_clm(xml_file))
