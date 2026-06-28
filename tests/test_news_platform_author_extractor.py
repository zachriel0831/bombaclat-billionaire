"""news_platform.author_extractor tests."""

import unittest

from news_platform.author_extractor import extract_authors_from_text, normalize_authors


class AuthorExtractorTests(unittest.TestCase):
    def test_extracts_ltn_reporter_byline(self):
        text = "〔記者張文川／台北報導〕理化老師變絕命毒師，判刑入獄。"
        self.assertEqual(extract_authors_from_text(text), ["張文川"])

    def test_extracts_only_real_ltn_byline_not_photo_credit(self):
        text = "2026/05/15 12:35 記者孫唯容／台北報導 受訪者說明。（記者孫唯容攝）"
        self.assertEqual(extract_authors_from_text(text), ["孫唯容"])

    def test_extracts_cna_reporter_with_location_suffix(self):
        text = "（中央社記者謝君臨台北14日電）立法院今天三讀通過。"
        self.assertEqual(extract_authors_from_text(text), ["謝君臨"])

    def test_does_not_extract_press_conference_as_reporter(self):
        text = "梁文傑在陸委會記者會表示，現在制度是這樣。"
        self.assertEqual(extract_authors_from_text(text), [])

    def test_does_not_extract_non_byline_reporter_mentions(self):
        text = "CNN記者：很不像他；救難人員表示仍有人不幸失聯。"
        self.assertEqual(extract_authors_from_text(text), [])

    def test_does_not_extract_news_slash_comprehensive_report_as_writer(self):
        text = "即時新聞／綜合報導 警消搜尋學生蹤跡，不幸失聯，其遺體在今晨尋獲。"
        self.assertEqual(extract_authors_from_text(text), [])

    def test_does_not_extract_press_conference_suffix_before_location(self):
        text = "記者何玉華／台北報導 張文潔陪同召開記者會的台北市議員說明。"
        self.assertEqual(extract_authors_from_text(text), ["何玉華"])

    def test_normalizes_explicit_author_values(self):
        values = ["reporter@example.com (Jane Doe)", "記者王小明／台北報導"]
        self.assertEqual(normalize_authors(values), ["Jane Doe", "王小明"])

    def test_rejects_publication_names(self):
        self.assertEqual(normalize_authors(["自由時報", "TVBS新聞網"]), [])

    def test_rejects_known_non_author_phrases(self):
        self.assertEqual(normalize_authors(["分析", "不幸失聯", "其遺體在今晨", "會表示", "會的"]), [])

    def test_rejects_detail_page_false_reporters(self):
        values = [
            "收停車費兄妹",
            "男子家屬",
            "附近民眾",
            "財經政治",
            "嫌犯蔡晉財",
            "中央社發布",
            "本刊編輯部",
            "立院直播",
            "不便評論細節",
            "中檢偵辦",
            "詢問表示",
            "電訪表示",
            "總財損約",
            "裁定陳男",
            "CTWANT",
            "造咖",
        ]
        self.assertEqual(normalize_authors(values), [])

    def test_normalizes_detail_page_suffix_variants(self):
        values = [
            "王朝鈺傳真",
            "王鴻國傳真",
            "朱蒲青專訪",
            "吳哲豪傳真",
            "陳韻聿倫敦",
            "中央社記者謝君臨台北14日電",
        ]
        self.assertEqual(normalize_authors(values), ["王朝鈺", "王鴻國", "朱蒲青", "吳哲豪", "陳韻聿", "謝君臨"])

    def test_trims_detail_page_role_suffixes(self):
        self.assertEqual(normalize_authors(["張柏源綜合報導", "鄭景議翻攝"]), ["張柏源", "鄭景議"])

    def test_trims_editor_prefixes(self):
        self.assertEqual(normalize_authors(["實習編輯林瑜", "責任編輯：王小明"]), ["林瑜", "王小明"])


if __name__ == "__main__":
    unittest.main()
