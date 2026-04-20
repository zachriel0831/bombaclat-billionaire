# Unit tests for the yfinance stocks scraper extraction logic.
# These tests do not hit the network — they feed a synthetic
# DataFrame (shape identical to yf.download output) into the
# pure extraction function and assert the derived fields.

import os
import sys
import unittest

# scrapers/yfinance_stocks.py does sys.path.insert(..., "src/"),
# and expects relay_client to be importable from there.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
sys.path.insert(0, os.path.join(SRC, "scrapers"))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

import yfinance_stocks  # noqa: E402


@unittest.skipIf(pd is None, "pandas not available")
class ExtractQuoteFromDownloadTests(unittest.TestCase):
    def _multi_index_df(self) -> "pd.DataFrame":
        # Mimic shape returned by yf.download(tickers="AAPL NVDA", group_by="column").
        idx = pd.date_range("2026-04-14", periods=3, freq="D")
        columns = pd.MultiIndex.from_tuples(
            [
                ("Close",  "AAPL"),
                ("Close",  "NVDA"),
                ("Volume", "AAPL"),
                ("Volume", "NVDA"),
            ]
        )
        data = [
            [180.0, 900.0, 1_000_000, 2_000_000],
            [181.0, 910.0, 1_100_000, 2_100_000],
            [182.5, 920.0, 1_200_000, 2_200_000],
        ]
        return pd.DataFrame(data, index=idx, columns=columns)

    def _single_symbol_df(self) -> "pd.DataFrame":
        idx = pd.date_range("2026-04-14", periods=3, freq="D")
        return pd.DataFrame(
            {
                "Close":  [100.0, 101.0, 102.0],
                "Volume": [500,   600,   700],
            },
            index=idx,
        )

    def test_multi_symbol_extract(self) -> None:
        df = self._multi_index_df()
        quote = yfinance_stocks._extract_quote_from_download(df, "AAPL", "Apple")
        self.assertIsNotNone(quote)
        self.assertEqual(quote["symbol"], "AAPL")
        self.assertEqual(quote["price"], 182.5)
        self.assertEqual(quote["prev_close"], 181.0)
        self.assertAlmostEqual(quote["change"], 1.5, places=4)
        self.assertAlmostEqual(quote["change_pct"], round(1.5 / 181.0 * 100, 2), places=2)
        self.assertEqual(quote["volume"], 1_200_000)

    def test_missing_symbol_returns_none(self) -> None:
        df = self._multi_index_df()
        self.assertIsNone(
            yfinance_stocks._extract_quote_from_download(df, "UNKNOWN", "??")
        )

    def test_single_symbol_extract(self) -> None:
        df = self._single_symbol_df()
        quote = yfinance_stocks._extract_quote_from_download(df, "FOO", "Foo")
        self.assertIsNotNone(quote)
        self.assertEqual(quote["price"], 102.0)
        self.assertEqual(quote["prev_close"], 101.0)
        self.assertEqual(quote["volume"], 700)

    def test_empty_df_returns_none(self) -> None:
        self.assertIsNone(
            yfinance_stocks._extract_quote_from_download(None, "AAPL", "Apple")
        )
        empty = pd.DataFrame()
        self.assertIsNone(
            yfinance_stocks._extract_quote_from_download(empty, "AAPL", "Apple")
        )


if __name__ == "__main__":
    unittest.main()
