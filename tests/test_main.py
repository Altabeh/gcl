import unittest
import warnings

from gcl import __version__
from gcl.main import GCLParse
from gcl.settings import root_dir
from gcl.utils import load_json


class TestGCLParse(unittest.TestCase):

    __case_id_list__ = ["3420814358029019827", "5200024483905774304"]

    def test_case_parse(self):
        """
        Test `.gcl_parse` method of the gcl class.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.assertEqual.__self__.maxDiff = None
            GCL = GCLParse(suffix=f"test_v{__version__}")
            for id_ in self.__case_id_list__:
                print(f"Started testing test_case_{id_}...")
                original_data = load_json(
                    root_dir / "tests" / "test_files" / f"test_case_{id_}.json"
                )
                GCL.gcl_parse(f"https://scholar.google.com/scholar_case?case={id_}")
                test_data = load_json(
                    GCL.data_dir / "json" / f"json_test_v{__version__}" / f"{id_}.json"
                )
                for k, v in test_data.items():
                    if v is None or isinstance(v, int):
                        self.assertEqual(v, original_data[k])
                        print(f"{k}: OK")
                    else:
                        if k != "html":
                            self.assertCountEqual(v, original_data[k])
                            print(f"{k}: OK")

            print(f"The case {id_} was successfully created and tested")


if __name__ == "__main__":
    unittest.main()
