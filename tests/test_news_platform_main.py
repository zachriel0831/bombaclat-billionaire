"""news_platform.main config tests."""

import os
import unittest

from news_platform.main import parse_categories, parse_public_sources


class MainConfigTests(unittest.TestCase):
    def test_parse_categories_accepts_aliases_and_dedupes(self):
        self.assertEqual(parse_categories("政治,society,politics"), ("politics", "society"))

    def test_parse_categories_uses_env_default(self):
        old_value = os.environ.get("NEWSPF_CATEGORIES")
        os.environ["NEWSPF_CATEGORIES"] = "politics"
        try:
            self.assertEqual(parse_categories(None), ("politics",))
        finally:
            if old_value is None:
                os.environ.pop("NEWSPF_CATEGORIES", None)
            else:
                os.environ["NEWSPF_CATEGORIES"] = old_value

    def test_parse_public_sources_normalizes_aliases(self):
        self.assertEqual(parse_public_sources("ly, legislative-bills,ly_bills"), ("ly_bills",))


if __name__ == "__main__":
    unittest.main()
