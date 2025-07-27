# Google Case Law Parser (GCL)

A Python package for parsing Google Case Law and Patent data.

## Features

- Parse Google Case Law pages
- Extract patent information
- Handle citations and references
- Support for Selenium-based scraping

## Installation

1. Clone the repository:
```bash
git clone https://github.com/alirezabehtash/gcl.git
cd gcl
```

2. Create and activate a virtual environment:
```bash
python3 -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
```

3. Install the package in development mode:
```bash
pip install -e .
```

## Docker Setup (Required for Scraping)

The package uses Selenium for scraping. To set up the Selenium container:

```bash
docker-compose up -d
```

## Quick Start

```python
from gcl import GCLParse
from pathlib import Path

# Initialize parser
data_dir = Path("data")  # Use the data directory in the project
parser = GCLParse(data_dir=data_dir)

# Parse a case law
case_law_url = "https://scholar.google.com/scholar_case?case=9862061449582190482"
case_data = parser.gcl_parse(
    case_law_url,
    skip_patent=True,  # Include patent data
    return_data=True,   # Return the parsed data
)

# Print basic information
print(f"Case ID: {case_data['id']}")
print(f"Court: {case_data['court']}")
if 'patents_in_suit' in case_data:
    print(f"Patents in suit: {case_data['patents_in_suit']}")
```

## Testing

The package includes a test suite to ensure functionality. To run the tests:

1. Make sure you have installed the package in development mode as described in the Installation section.

2. Run the tests using unittest:
```bash
python -m unittest tests/test_main.py
```

The test suite includes:
- Case law parsing tests with sample cases
- Data structure validation
- JSON output verification

Each test case compares the parsed output against known correct results stored in `tests/test_files/`.

## License

MIT 