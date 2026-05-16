"""news_platform.article_detail_author_extractor tests."""

import unittest

from news_platform.article_detail_author_extractor import ArticleDetailAuthorExtractor
from news_platform.author_metadata import (
    AUTHOR_METHOD_ARTICLE_DETAIL,
    AUTHOR_STATUS_NO_AUTHOR_METADATA,
    AUTHOR_STATUS_PRESENT,
)


class ArticleDetailAuthorExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = ArticleDetailAuthorExtractor()

    def test_extracts_json_ld_author(self) -> None:
        html = """
        <html><head>
          <script type="application/ld+json">
            {"@type":"NewsArticle","author":[{"@type":"Person","name":"陳俊華"}]}
          </script>
        </head><body></body></html>
        """

        result = self.extractor.extract(html)

        self.assertEqual(result.status, AUTHOR_STATUS_PRESENT)
        self.assertEqual(result.method, AUTHOR_METHOD_ARTICLE_DETAIL)
        self.assertEqual(result.authors, ["陳俊華"])
        self.assertEqual(result.confidence, 0.95)

    def test_extracts_meta_author_byline(self) -> None:
        html = '<html><head><meta name="author" content="記者王小明／台北報導"></head></html>'

        result = self.extractor.extract(html)

        self.assertEqual(result.status, AUTHOR_STATUS_PRESENT)
        self.assertEqual(result.authors, ["王小明"])

    def test_extracts_visible_cna_byline_window(self) -> None:
        html = "<html><body><nav>首頁 政治 社會</nav><p>中央社記者李小華台北15日電，今日...</p></body></html>"

        result = self.extractor.extract(html)

        self.assertEqual(result.status, AUTHOR_STATUS_PRESENT)
        self.assertEqual(result.authors, ["李小華"])

    def test_does_not_treat_interview_question_as_byline(self) -> None:
        html = "<html><body><p>新北市長參選人蘇巧慧vs.記者：「我想我們新北市是全國人口最多的城市。」</p></body></html>"

        result = self.extractor.extract(html)

        self.assertEqual(result.status, AUTHOR_STATUS_NO_AUTHOR_METADATA)
        self.assertEqual(result.authors, [])

    def test_does_not_treat_press_conference_text_as_ltn_byline(self) -> None:
        html = """
        <html><body>
          <p>梁文傑在陸委會記者會表示，現在制度是這樣。</p>
          <p>救難人員表示仍有人不幸失聯。</p>
        </body></html>
        """

        result = self.extractor.extract(html)

        self.assertEqual(result.status, AUTHOR_STATUS_NO_AUTHOR_METADATA)
        self.assertEqual(result.authors, [])

    def test_returns_no_author_metadata_for_empty_page(self) -> None:
        html = "<html><body><article><h1>新聞標題</h1><p>只有正文摘要。</p></article></body></html>"

        result = self.extractor.extract(html)

        self.assertEqual(result.status, AUTHOR_STATUS_NO_AUTHOR_METADATA)
        self.assertEqual(result.authors, [])


if __name__ == "__main__":
    unittest.main()
