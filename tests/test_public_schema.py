import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from materialize import PUBLIC_TABLES  # noqa: E402


class PublicSchemaTests(unittest.TestCase):
    def test_expected_public_tables(self) -> None:
        self.assertEqual(
            set(PUBLIC_TABLES),
            {
                "Anchor_Drugs",
                "Anchor_Drugs_And_Synonyms",
                "Anchor_Drug_Source",
                "Anchor_Drug_Synonym_Source",
                "Anchor_Regimen",
                "Regimens_And_Synonyms",
                "Regimen_Source",
                "Anchor_Drugs_To_Regimens",
                "Conditions_And_Regimens",
                "Clinical_Trials",
                "Data_Sources",
            },
        )


if __name__ == "__main__":
    unittest.main()

