import unittest
import warnings
import os
from gcl import __version__
from gcl.google_patents_scrape import GooglePatents


class TestGooglePatents(unittest.TestCase):
    __test_patents__ = [
        "US8463717B2",  # System and method for analyzing patent value
        "US8570814B2",  # Memory controller
        "US7654321B2",  # Sample patent
        "US8234567B2",  # Another sample
    ]

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
                "US8463717B2",  # Using a sample patent number
                just_claims=True,
                skip_patent=False,
                return_data=["claims"],
                no_save=True,
            )
            # Basic validation of the claims dictionary structure
            self.assertIsInstance(claims, dict)
            if claims:  # If claims were found
                for claim_num, claim_text in claims.items():
                    self.assertIsInstance(claim_num, int)
                    self.assertIsInstance(claim_text, str)
                    self.assertTrue(len(claim_text) > 0)

            # Verify file was not created
            file_path = os.path.join(
                "tests",
                "patent",
                f"patent_test_v{__version__}",
                "US8570814B2",
                "US8570814B2.json",
            )
            self.assertFalse(
                os.path.exists(file_path),
                "File should not be created when no_save=True",
            )

    def test_concurrent_claims(self):
        """
        Test concurrent processing of multiple patents' claims using async scraper.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.assertEqual.__self__.maxDiff = None

            # Initialize parser with test directory
            gp = GooglePatents(data_dir="tests", suffix=f"test_v{__version__}")

            # Process multiple patents concurrently
            results = gp.download_patents_concurrently(
                patents=self.__test_patents__,
                max_workers=4,
                just_claims=True,
                no_save=True,
            )

            # Validate results
            self.assertEqual(len(results), len(self.__test_patents__))

            # Count successful downloads
            successful_downloads = sum(1 for found, _ in results if found)
            self.assertGreater(
                successful_downloads,
                0,
                "At least one patent should be downloaded successfully",
            )

            for found, claims in results:
                # Verify each successful result has valid claims
                if found:
                    self.assertIsInstance(claims, dict)
                    self.assertTrue(
                        len(claims) > 0, "Claims dictionary should not be empty"
                    )

                    for claim_num, claim_text in claims.items():
                        self.assertIsInstance(claim_num, int)
                        self.assertIsInstance(claim_text, str)
                        self.assertTrue(len(claim_text) > 0)
                else:
                    # For failed downloads, claims should be None
                    self.assertIsNone(claims)

            # Verify no files were created
            for patent in self.__test_patents__:
                file_path = os.path.join(
                    "tests",
                    "patent",
                    f"patent_test_v{__version__}",
                    patent,
                    f"{patent}.json",
                )
                self.assertFalse(
                    os.path.exists(file_path),
                    f"File should not be created when no_save=True: {file_path}",
                )

    def test_concurrent_full_data(self):
        """
        Test concurrent processing of multiple patents with full data.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.assertEqual.__self__.maxDiff = None

            # Initialize parser with test directory
            gp = GooglePatents(data_dir="tests", suffix=f"test_v{__version__}")

            # Process multiple patents concurrently with full data
            results = gp.download_patents_concurrently(
                patents=self.__test_patents__[
                    :2
                ],  # Use fewer patents for full data test
                max_workers=2,
                just_claims=False,
                no_save=True,
            )

            # Validate results
            self.assertEqual(len(results), 2)

            for found, data in results:
                if found:
                    # Verify full patent data structure
                    self.assertIsInstance(data, dict)
                    self.assertIn("patent_number", data)
                    self.assertIn("url", data)
                    self.assertIn("title", data)
                    self.assertIn("abstract", data)
                    self.assertIn("claims", data)

                    # Verify claims data
                    self.assertIsInstance(data["claims"], dict)
                    self.assertTrue(len(data["claims"]) > 0)

                    # Verify at least one claim has content
                    some_claim = next(iter(data["claims"].values()))
                    self.assertIn("context", some_claim)
                    self.assertTrue(len(some_claim["context"]) > 0)
                else:
                    self.assertIsNone(data)
