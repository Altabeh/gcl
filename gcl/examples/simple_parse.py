from gcl import GCLParse
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize parser with a custom data directory
data_dir = Path("example_data")
parser = GCLParse(data_dir=data_dir, suffix="example")

# Example case law URL
case_law_url = "https://scholar.google.com/scholar_case?case=4398438352003003603"

try:
    # Parse the case and get the data
    case_data = parser.gcl_parse(
        case_law_url,
        skip_patent=False,  # Include patent data
        return_data=True,   # Return the parsed data
    )
    
    # Print some basic information
    print(f"\nCase ID: {case_data['id']}")
    print(f"Court: {case_data['court']}")
    if 'patents_in_suit' in case_data:
        print(f"Patents in suit: {case_data['patents_in_suit']}")
        
except Exception as e:
    logging.error(f"Error parsing case law: {str(e)}")
    raise 