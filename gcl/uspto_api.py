"""
This module provides a python wrapper for USPTO Open Data Portal (ODP) API.

The offered features include downloading, parsing and serializing
patent application data, bulk search and download, and more.

Copyright (c) 2025 Alireza Behtash
Licensed under the MIT License (see LICENSE file)
"""

import requests
import re
import json
from time import sleep
from zipfile import ZipFile
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Union
from bs4 import BeautifulSoup as BS
from .regexes import PTABRegex
from .utils import (
    rm_repeated,
    deaccent,
    regex,
    create_dir,
    load_json,
    closest_value,
    timestamp,
    parser,
)
from functools import reduce
from operator import concat


logger = logging.getLogger(__name__)

__all__ = ["USPTOAPIMixin"]


class USPTOAPIMixin(PTABRegex):
    """Mixin class that adds USPTO API functionality to GCLParse."""

    def __init__(self, **kwargs):
        """Initialize USPTO API functionality."""
        # Initialize with default values
        self.uspto_api_key = None
        self.uspto_base_url = None
        self.uspto_headers = None
        self.use_uspto_api = False

        # Initialize API if key is provided
        if api_key := kwargs.get("uspto_api_key") or os.getenv("USPTO_API_KEY"):
            self.uspto_api_key = api_key
            self.uspto_base_url = "https://api.uspto.gov/api/v1"
            self.uspto_headers = {
                "X-API-KEY": self.uspto_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            self.use_uspto_api = True

        # Call parent class initialization
        super().__init__(**kwargs)

    def _search_applications(
        self,
        query: Optional[str] = None,
        filters: Optional[List[Dict]] = None,
        range_filters: Optional[List[Dict]] = None,
        sort: Optional[List[Dict]] = None,
        fields: Optional[List[str]] = None,
        offset: int = 0,
        limit: int = 25,
        facets: Optional[List[str]] = None,
    ) -> Dict:
        """
        Search patent applications using the USPTO API.

        Args:
            query: Search query string (supports boolean operators, wildcards, exact phrases)
            filters: List of field filters [{"name": field_name, "value": [value1, value2]}]
            range_filters: List of range filters [{"field": name, "valueFrom": start, "valueTo": end}]
            sort: List of sort fields [{"field": name, "order": "asc/desc"}]
            fields: List of fields to return
            offset: Starting position (pagination)
            limit: Number of results to return
            facets: List of fields to facet on

        Returns:
            API response data or None if API is not enabled
        """
        if not self.use_uspto_api:
            return None

        try:
            payload = {
                "q": query or "",
                "pagination": {"offset": offset, "limit": limit},
            }

            if filters:
                payload["filters"] = filters
            if range_filters:
                payload["rangeFilters"] = range_filters
            if sort:
                payload["sort"] = sort
            if fields:
                payload["fields"] = fields
            if facets:
                payload["facets"] = facets

            response = requests.post(
                f"{self.uspto_base_url}/patent/applications/search",
                headers=self.uspto_headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error searching applications: {str(e)}")
            return None

    def _get_application(self, application_number: str) -> Optional[Dict]:
        """
        Get detailed information about a specific patent application.

        Args:
            application_number: The application number to look up

        Returns:
            Application data or None if API is not enabled or error occurs
        """
        if not self.use_uspto_api:
            return None

        try:
            response = requests.get(
                f"{self.uspto_base_url}/patent/applications/{application_number}",
                headers=self.uspto_headers,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting application {application_number}: {str(e)}")
            return None

    def _get_application_metadata(self, application_number: str) -> Optional[Dict]:
        """
        Get metadata for a specific application.

        Returns:
            Application metadata or None if API is not enabled or error occurs
        """
        if not self.use_uspto_api:
            return None

        try:
            response = requests.get(
                f"{self.uspto_base_url}/patent/applications/{application_number}/meta-data",
                headers=self.uspto_headers,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting metadata for {application_number}: {str(e)}")
            return None

    def _get_application_assignments(self, application_number: str) -> Optional[Dict]:
        """
        Get assignment data for a specific application.

        Returns:
            Assignment data or None if API is not enabled or error occurs
        """
        if not self.use_uspto_api:
            return None

        try:
            response = requests.get(
                f"{self.uspto_base_url}/patent/applications/{application_number}/assignment",
                headers=self.uspto_headers,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(
                f"Error getting assignments for {application_number}: {str(e)}"
            )
            return None

    def _get_application_transactions(self, application_number: str) -> Optional[Dict]:
        """
        Get transaction history for a specific application.

        Returns:
            Transaction data or None if API is not enabled or error occurs
        """
        if not self.use_uspto_api:
            return None

        try:
            response = requests.get(
                f"{self.uspto_base_url}/patent/applications/{application_number}/transactions",
                headers=self.uspto_headers,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(
                f"Error getting transactions for {application_number}: {str(e)}"
            )
            return None

    def _get_application_documents(self, application_number: str) -> Optional[Dict]:
        """
        Get document details for a specific application.

        Returns:
            Document data or None if API is not enabled or error occurs
        """
        if not self.use_uspto_api:
            return None

        try:
            response = requests.get(
                f"{self.uspto_base_url}/patent/applications/{application_number}/documents",
                headers=self.uspto_headers,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting documents for {application_number}: {str(e)}")
            return None

    def _search_bulk_datasets(
        self,
        query: Optional[str] = None,
        sort: Optional[str] = None,
        offset: int = 0,
        limit: int = 25,
        facets: Optional[List[str]] = None,
        fields: Optional[List[str]] = None,
        filters: Optional[List[Dict]] = None,
        range_filters: Optional[List[Dict]] = None,
    ) -> Optional[Dict]:
        """
        Search USPTO bulk datasets.

        Args:
            query: Search query string
            sort: Sort field and order (e.g., "name asc")
            offset: Starting position
            limit: Number of results
            facets: List of fields to facet on
            fields: List of fields to return
            filters: List of field filters [{"name": field_name, "value": [value1, value2]}]
            range_filters: List of range filters [{"field": name, "valueFrom": start, "valueTo": end}]

        Returns:
            Search results or None if API is not enabled or error occurs
        """
        if not self.use_uspto_api:
            return None

        try:
            params = {
                "q": query or "",
                "offset": offset,
                "limit": limit,
            }
            if sort:
                params["sort"] = sort
            if facets:
                params["facets"] = ",".join(facets)
            if fields:
                params["fields"] = ",".join(fields)
            if filters:
                params["filters"] = filters
            if range_filters:
                params["rangeFilters"] = range_filters

            response = requests.get(
                f"{self.uspto_base_url}/datasets/products/search",
                headers=self.uspto_headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error searching bulk datasets: {str(e)}")
            return None

    def _get_application_bulk_documents(
        self,
        appl_number: str,
        doc_codes: list = None,
        mime_types: list = None,
        close_to_date: str = None,
        skip_download: bool = False,
    ) -> List[Path]:
        """
        Get application documents from USPTO API.

        Args:
            appl_number: Application number
            doc_codes: List of document codes to filter by (e.g., ["CLM", "SPEC"])
            mime_types: List of MIME types to filter by (e.g., ["XML", "PDF"])
            close_to_date: Filter for documents closest to this date (YYYY-MM-DD)
            skip_download: If True, only return metadata without downloading files

        Returns:
            List of paths to downloaded files
        """
        if not self.use_uspto_api:
            return []

        try:
            # Create transactions folder
            transactions_folder = create_dir(
                self.data_dir
                / "uspto"
                / "ifw"
                / f"transactions_{self.suffix}"
                / appl_number
            )

            # Try to load existing transactions
            transactions_file = transactions_folder / f"{appl_number}.json"
            if transactions_file.is_file():
                transactions = load_json(transactions_file)
            else:
                # Get documents from API
                response = requests.get(
                    f"{self.uspto_base_url}/patent/applications/{appl_number}/documents",
                    headers=self.uspto_headers,
                )
                response.raise_for_status()
                transactions = response.json()

                # Save transactions
                with open(transactions_file, "w") as f:
                    json.dump(transactions, f, indent=4)

            if not transactions or "documentBag" not in transactions:
                logger.error(f"No documents found for application {appl_number}")
                return []

            documents = transactions["documentBag"]

            # Filter by document codes
            if doc_codes:
                documents = [
                    doc for doc in documents if doc.get("documentCode") in doc_codes
                ]

            # Filter by date if specified
            if close_to_date:
                if documents:
                    try:
                        target_date = int(timestamp(close_to_date))
                        doc_dates = [
                            (doc, int(timestamp(doc["officialDate"])))
                            for doc in documents
                        ]
                        closest_idx = closest_value(
                            [date for _, date in doc_dates],
                            target_date,
                            none_allowed=False,
                        )
                        documents = [doc_dates[closest_idx][0]]
                    except (TypeError, ValueError) as e:
                        logger.error(f"Error filtering by date: {str(e)}")
                        documents = []

            if skip_download:
                return []

            downloaded_files = []
            for doc in documents:
                # Get download options
                download_options = doc.get("downloadOptionBag", [])

                # Filter by mime type if specified
                if mime_types:
                    download_options = [
                        opt
                        for opt in download_options
                        if opt.get("mimeTypeIdentifier") in mime_types
                    ]

                for opt in download_options:
                    mime_type = opt.get("mimeTypeIdentifier")
                    if not mime_type:
                        continue

                    # Format filename
                    mail_date = parser.parse(doc["officialDate"]).strftime("%Y-%m-%d")
                    file_name = f"{doc['documentIdentifier']}_{appl_number}_{mail_date}_{doc['documentCode']}.{mime_type.lower()}"
                    output_path = transactions_folder / file_name

                    # Skip if file exists
                    if output_path.exists():
                        downloaded_files.append(output_path)
                        continue

                    # Download file
                    if download_url := opt.get("downloadUrl"):
                        try:
                            response = requests.get(
                                download_url, headers=self.uspto_headers, stream=True
                            )
                            response.raise_for_status()

                            with open(output_path, "wb") as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)

                            logger.info(f"Downloaded {file_name}")
                            downloaded_files.append(output_path)

                            # Extract if zip file
                            if output_path.suffix.lower() == ".zip":
                                with ZipFile(output_path, "r") as zipf:
                                    zipf.extractall(transactions_folder)
                                output_path.unlink()

                        except Exception as e:
                            logger.error(f"Error downloading {file_name}: {str(e)}")

                    sleep(1)  # Rate limiting

            return rm_repeated(downloaded_files)

        except Exception as e:
            logger.error(f"Error getting documents for {appl_number}: {str(e)}")
            return []

    def parse_clm(self, xml_file: Union[Path, str]) -> dict:
        """
        Parse the xml file for the claims, i.e. items having the code "CLM"
        in the transaction history between applicant and the USPTO office .
        """
        if not isinstance(xml_file, Path):
            xml_file = Path(xml_file)

        clm = BS(deaccent(xml_file.read_text(errors="ignore")), features="lxml")
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
