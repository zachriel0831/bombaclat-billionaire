import unittest

from news_collector.sources.gdelt import _parse_gdelt_payload


class GdeltSourceTests(unittest.TestCase):
    def test_parse_payload_ok(self) -> None:
        payload = _parse_gdelt_payload('{"articles": []}')
        self.assertIsInstance(payload, dict)
        self.assertIn("articles", payload)

    def test_parse_payload_empty_body(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            _parse_gdelt_payload("   ")
        self.assertIn("empty response body", str(ctx.exception))

    def test_parse_payload_plain_rate_limit_text(self) -> None:
        body = "Please limit requests to one every 5 seconds or contact ..."
        with self.assertRaises(RuntimeError) as ctx:
            _parse_gdelt_payload(body)
        self.assertIn("429", str(ctx.exception))

    def test_parse_payload_non_json_body(self) -> None:
        body = "<html><title>Service Unavailable</title></html>"
        with self.assertRaises(RuntimeError) as ctx:
            _parse_gdelt_payload(body)
        self.assertIn("non-JSON body", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
