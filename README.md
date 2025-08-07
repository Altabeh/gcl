# Google Case Law Parser (GCL)

A powerful Python package for parsing and analyzing Google Case Law and Patent data. This tool provides comprehensive functionality for extracting, parsing, and analyzing legal documents from Google Scholar's case law database, with additional support for patent information extraction and analysis.

## Features

### Case Law Parsing
- Extract comprehensive case information including:
  - Full case name and citation
  - Court information and jurisdiction
  - Decision date
  - Judge names and personal opinions (concurrences/dissents)
  - Case numbers and docket information
  - Bluebook citations
  - Footnotes and references
  - Page numbers and structure

### Patent Analysis
- Extract and analyze patent information:
  - Identify patents-in-suit
  - Parse patent claims
  - Track claim citations
  - Handle patent application numbers
  - Link to USPTO data
  - Monitor patent transaction history

### Advanced Text Processing
- Semantic parsing of legal documents
- Bluebook citation formatting and validation
- Court and jurisdiction identification
- Structured data extraction
- Support for multiple citation formats
- Footnote and reference management

### Data Management
- JSON serialization of parsed data
- CSV export capabilities
- Structured data organization
- Support for batch processing
- Caching and data persistence

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

## Dependencies

The package requires the following main dependencies:
- beautifulsoup4 (≥4.12.2) - HTML parsing
- requests (≥2.31.0) - HTTP requests
- selenium (≥4.0.0) - Web scraping
- reporters-db (≥3.2.56) - Legal reporter database
- Additional dependencies listed in requirements.txt

## Docker Setup (Required for Scraping)

The package uses Selenium for web scraping. To set up the Selenium container:

```bash
docker-compose up -d
```

## Usage

### Basic Case Law Parsing

```python
from gcl import GCLParse
from pathlib import Path

# Initialize parser
data_dir = Path("data")
parser = GCLParse(data_dir=data_dir)

# Parse a case law
case_law_url = "https://scholar.google.com/scholar_case?case=9862061449582190482"
case_data = parser.gcl_parse(
    case_law_url,
    skip_patent=False,  # Include patent data
    return_data=True,   # Return the parsed data
)

# Access parsed data
print(f"Case Name: {case_data['full_case_name']}")
print(f"Court: {case_data['court']}")
print(f"Date: {case_data['date']}")
print(f"Judges: {case_data['judges']}")
```

### Working with Citations

```python
# Get Bluebook citation
citation = parser.gcl_citor(case_law_url)
print(f"Bluebook Citation: {citation}")

# Get citation summary
summary = parser.gcl_citation_summary(case_data['id'])
print(f"Citation Summary: {summary}")
```

### Patent Analysis

```python
# Parse case with patent information
case_data = parser.gcl_parse(
    case_law_url,
    skip_patent=False,
    skip_application=False
)

# Access patent information
for patent in case_data['patents_in_suit']:
    print(f"Patent Number: {patent['patent_number']}")
    print(f"Application Number: {patent['application_number']}")
    print(f"Cited Claims: {patent['cited_claims']}")
```

### Batch Processing

```python
# Create a list of case summaries
parser.gcl_make_list("case_summaries")

# Bundle citations from multiple cases
parser.gcl_bundle_cites(blue_citation=True)
```

## Advanced Features

### Personal Opinions Analysis
The package can identify and extract personal opinions (concurrences and dissents):

```python
if case_data['personal_opinions']['concur']:
    for opinion in case_data['personal_opinions']['concur']:
        print(f"Concurring Judge: {opinion['judge']}")
        print(f"Opinion Location: {opinion['index_span']}")
```

### Citation Network Analysis
Extract and analyze citation networks within cases:

```python
# Get all citations in a case
citations = case_data['cites_to']
for case_id, citations in citations.items():
    print(f"Cited Case: {case_id}")
    for citation in citations:
        print(f"Citation Format: {citation['citation']}")
```

## Testing

The package includes a comprehensive test suite:

1. Ensure development installation:
```bash
pip install -e .
```

2. Run the tests:
```bash
python -m unittest tests/test_main.py
```

The test suite covers:
- Case law parsing accuracy
- Citation formatting
- Patent data extraction
- Data structure validation
- JSON serialization
- Error handling

## Project Structure

```
gcl/
├── gcl/
│   ├── __init__.py
│   ├── main.py           # Core parsing functionality
│   ├── google_patents_scrape.py
│   ├── uspto_api.py      # USPTO API integration
│   ├── proxy.py          # Proxy management
│   ├── regexes.py        # Regular expressions
│   ├── settings.py       # Configuration
│   └── utils.py          # Utility functions
├── tests/
│   ├── test_main.py
│   └── test_files/       # Test case data
├── docker-compose.yml    # Docker configuration
└── requirements.txt      # Dependencies
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

Alireza Behtash

Copyright (c) 2025 Alireza Behtash