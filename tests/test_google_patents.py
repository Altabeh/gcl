import unittest
import warnings
import os
from gcl import __version__
from gcl.google_patents_scrape import GooglePatents

class TestGooglePatents(unittest.TestCase):
    def test_just_claims(self):
        """
        Test the just_claims parameter of the patent_data method.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.assertEqual.__self__.maxDiff = None
            
            gp = GooglePatents(data_dir="tests", suffix=f"test_v{__version__}")
            
            # Test with a known patent number and no_save=True
            found, claims = gp.patent_data(
                "US7654321",  # Using a sample patent number
                just_claims=True,
                skip_patent=False,
                no_save=True
            )
            
            # Basic validation of the claims dictionary structure
            self.assertIsInstance(claims, dict)
            if claims:  # If claims were found
                for claim_num, claim_text in claims.items():
                    self.assertIsInstance(claim_num, int)
                    self.assertIsInstance(claim_text, str)
                    self.assertTrue(len(claim_text) > 0)
            
            # Verify file was not created
            file_path = os.path.join("tests", "patent", f"patent_test_v{__version__}", "US7654321", "US7654321.json")
            self.assertFalse(os.path.exists(file_path), "File should not be created when no_save=True")