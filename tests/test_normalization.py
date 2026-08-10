import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common import normalize_surface, valid_surface  # noqa: E402


class NormalizationTests(unittest.TestCase):
    def test_normalizes_case_and_whitespace(self) -> None:
        self.assertEqual(normalize_surface("  5-FU\t\n"), "5-fu")

    def test_rejects_literal_null_placeholders(self) -> None:
        for value in ("", "none", "NULL", " n/a ", "unknown"):
            self.assertFalse(valid_surface(value))


if __name__ == "__main__":
    unittest.main()

