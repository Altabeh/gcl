
![gcl|test](https://github.com/StacksLaw/gcl/actions/workflows/tests.yml/badge.svg)


# gcl

This package provides a scraper/parser for Google case law pages available at https://scholar.google.com/.

The offered features include scraping, parsing, serializing
and tagging important data such as bluebook citations, judge names, courts,
decision dates, case numbers, patents in suit, cited claims, footnotes and etc.

# Getting started

### Install

After cloning the github repo `gcl`, you should go to the directory where the repo is downloaded, create a virtual python enviroment and run the following command on the terminal:

`pip install .`

to install the package. Make sure that once `selenium` is installed, you have the chromedriver installed as well. For macOS, we can do this by executing the following command on the terminal:

`brew cask install chromedriver`

### Test

To run gcl's test unit, just run the following command:

`python3 test.py`

### Try

To scrape and download a case law page, let us choose a case law page

https://scholar.google.com/scholar_case?case=9862061449582190482

and use the following snippet to get things started:

```
from gcl.gcl import GCLParse

GCL = GCLParse(data_dir="/users/.../gcl_test", suffix="test_v1")

case_law_url = "https://scholar.google.com/scholar_case?case=9862061449582190482"

GCL.gcl_parse(case_law_url, skip_patent=False, return_data=False, need_proxy=False, random_sleep=False,)
```

Running this code will save a JSON file `9862061449582190482.json` under the directory `/users/.../gcl_test/data/json/json_test_v1` with the following data structure:

```
{   
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
```

**Note:** `need_proxy` is advised to be set to `False` for now since it is still experimental and therefore not recommended to be turned on in this preliminary version. This has the caveat that we cannot run the `GCL` instance in parallel to make multiple queries to Google Scholar as your IP will be temporarily blocked. In the next version, we will make multiple querying operational.

# Updates

### v1.2

- An independent module `google_patent_api.py` is added to scrape patent data.
- EPO patents are now downloadable without claims missing.
- Patent data can now contain patent descriptions using the option `include_description = True` in `.patent_data()` of the GCLParse class.
- Claim/description extraction is more fine-grained and robust.
- `depdendent_on` value for each claim in `patents_in_suit` is now a list. It can take more than one value in case there are references to more than one precedeng claim.
- The method `.grab_ifw()` of the USPTOscrape class can take `skip_download` argument now to avoid sending requests in case the data file already exists in the local disk.
- Bug fixes
