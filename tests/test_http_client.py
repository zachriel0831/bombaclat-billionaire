import unittest
from unittest.mock import patch

from news_collector.http_client import http_get_text


class _FakeHeaders:
    def __init__(self, charset: str | None) -> None:
        self._charset = charset

    def get_content_charset(self) -> str | None:
        return self._charset


class _FakeResponse:
    def __init__(self, payload: bytes, charset: str | None) -> None:
        self._payload = payload
        self.headers = _FakeHeaders(charset)

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class HttpClientEncodingTests(unittest.TestCase):
    def test_http_get_text_honors_response_charset(self) -> None:
        payload = "中央社即時新聞 財經新聞".encode("cp950")
        with patch(
            "news_collector.http_client.urlopen",
            return_value=_FakeResponse(payload, "cp950"),
        ):
            text = http_get_text("https://example.com/feed.xml")

        self.assertEqual(text, "中央社即時新聞 財經新聞")

    def test_http_get_text_falls_back_to_xml_declared_charset(self) -> None:
        xml = '<?xml version="1.0" encoding="big5"?><rss><channel><title>新頭殼 - 財經</title></channel></rss>'
        payload = xml.encode("big5")
        with patch(
            "news_collector.http_client.urlopen",
            return_value=_FakeResponse(payload, None),
        ):
            text = http_get_text("https://example.com/feed.xml")

        self.assertIn("新頭殼 - 財經", text)


if __name__ == "__main__":
    unittest.main()
