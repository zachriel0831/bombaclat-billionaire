import unittest
from datetime import date

from news_collector.relay_bridge import _quote_to_payload
from news_collector.us_index_tracker import IndexQuote, UsIndexTracker


class UsIndexTrackerTests(unittest.TestCase):
    def test_parse_quote(self) -> None:
        tracker = UsIndexTracker(timeout_seconds=5)
        result = {
            "meta": {
                "symbol": "^DJI",
                "currentTradingPeriod": {
                    "regular": {
                        "start": 1772797800,
                        "end": 1772821200,
                    }
                },
            },
            "timestamp": [1772797860, 1772797920],
            "indicators": {
                "quote": [
                    {
                        "open": [47001.0, 47020.5],
                        "close": [47010.0, 47030.0],
                    }
                ]
            },
        }

        quote = tracker._parse_quote(result=result, label="DJIA", url="https://finance.yahoo.com/quote/%5EDJI")

        self.assertIsNotNone(quote)
        assert quote is not None
        self.assertEqual(quote.symbol, "DJIA")
        self.assertEqual(quote.open_price, 47001.0)
        self.assertEqual(quote.last_price, 47030.0)
        self.assertEqual(quote.regular_start_epoch, 1772797800)
        self.assertEqual(quote.regular_end_epoch, 1772821200)

    def test_format_messages(self) -> None:
        tracker = UsIndexTracker(timeout_seconds=5)
        quotes = {
            "DJIA": IndexQuote(
                symbol="DJIA",
                label="DJIA",
                url="https://finance.yahoo.com/quote/%5EDJI",
                trade_date=date(2026, 3, 9),
                regular_start_epoch=1772797800,
                regular_end_epoch=1772821200,
                open_price=47001.25,
                last_price=47123.5,
            ),
            "S&P 500": IndexQuote(
                symbol="S&P 500",
                label="S&P 500",
                url="https://finance.yahoo.com/quote/%5EGSPC",
                trade_date=date(2026, 3, 9),
                regular_start_epoch=1772797800,
                regular_end_epoch=1772821200,
                open_price=6100.5,
                last_price=6122.75,
            ),
        }

        open_text = tracker.format_open_message(date(2026, 3, 9), quotes)
        close_text = tracker.format_close_message(date(2026, 3, 9), quotes)

        self.assertIn("[US_INDEX_OPEN] 2026-03-09", open_text)
        self.assertIn("47,001.25", open_text)
        self.assertIn("6,122.75", close_text)

    def test_quote_to_payload(self) -> None:
        quote = IndexQuote(
            symbol="DJIA",
            label="DJIA",
            url="https://finance.yahoo.com/quote/%5EDJI",
            trade_date=date(2026, 3, 9),
            regular_start_epoch=1772797800,
            regular_end_epoch=1772821200,
            open_price=47001.25,
            last_price=47123.5,
        )

        payload = _quote_to_payload(quote)

        self.assertEqual(payload["symbol"], "DJIA")
        self.assertEqual(payload["label"], "DJIA")
        self.assertEqual(payload["open_price"], 47001.25)
        self.assertEqual(payload["last_price"], 47123.5)


if __name__ == "__main__":
    unittest.main()
