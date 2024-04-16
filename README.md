```
![gcl|test](https://github.com/Altabeh/gcl/actions/workflows/tests.yml/badge.svg)

# gcl

This package provides a scraper/parser for Google case law pages available at https://scholar.google.com/.

The offered features include scraping, parsing, serializing, and tagging important data such as bluebook citations, judge names, courts, decision dates, case numbers, patents in suit, cited claims, footnotes, etc.

# Getting started

### Install

After cloning the GitHub repo `gcl`, you should go to the directory where the repository is downloaded, create a virtual Python environment, and run the following command in the terminal:

`pip install .`

to install the package. Make sure that once `selenium` is installed, you have the Chrome driver installed as well. For macOS, we can do this by executing the following command in the terminal:

`brew install chromedriver --cask`

### Test

To run gcl's test unit, just run the following command:

`python -m unittest discover`

### Try

To scrape and download a case law page, let us choose a case law page,

https://scholar.google.com/scholar_case?case=9862061449582190482

and use the following snippet to get things started:

```python
from gcl.main import GCLParse

GCL = GCLParse(data_dir="/users/.../gcl_test", suffix="test_v1")

case_law_url = "https://scholar.google.com/scholar_case?case=9862061449582190482"

GCL.gcl_parse(case_law_url, skip_patent=False, return_data=False, need_proxy=False, random_sleep=False)
```

Running this code will save a JSON file `9862061449582190482.json` under the directory `/users/.../gcl_test/data/json/json_test_v1` with the following data structure:

```json
{   
    "id": null,
    "full_case_name": null,
    "case_numbers": [],
    "citation": null,
    "short_citation": [],
    "first_page": null,
    "last_page": null,
    "cites_to": {},
    "date": null,
    "court": {},
    "judges": [],
    "personal_opinions": {},
    "patents_in_suit": [],
    "html": null,
    "training_text": null,
    "footnotes": []
}
```

**Note:** `need_proxy` is advised to be set to `False` for now since it is still experimental and therefore not recommended to be turned on in this preliminary version. This has the caveat that we cannot run the `GCL` instance in parallel to make multiple queries to Google Scholar as your IP will be temporarily blocked. In the next version, we will make multiple parallel queries operational.
```