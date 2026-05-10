"""news_platform.keyword_extractor 測試 — 用真實 jieba 跑，需要 jieba 已安裝。"""

import unittest

from news_platform.keyword_extractor import KeywordExtractor


class KeywordExtractorTests(unittest.TestCase):
    def setUp(self):
        self.extractor = KeywordExtractor(top_k=5, min_keyword_length=2)

    def test_returns_empty_for_blank_input(self):
        self.assertEqual(self.extractor.extract(None), [])
        self.assertEqual(self.extractor.extract(""), [])
        self.assertEqual(self.extractor.extract("   "), [])

    def test_extracts_some_keywords_from_society_title(self):
        title = "高雄民宅丟煙火彈滾到隔壁鄰居家爆炸　恐怖前夫被捕"
        result = self.extractor.extract(title)
        self.assertGreater(len(result), 0)
        # 抽出的每筆都是 (keyword, score) 且 score 是 float
        for kw, score in result:
            self.assertIsInstance(kw, str)
            self.assertIsInstance(score, float)
            self.assertGreaterEqual(len(kw), 2)

    def test_filters_stopwords(self):
        # 「快訊」與「網友」都在 stopwords_tw.txt 內，不應出現在結果
        title = "快訊　網友爆料知名藝人涉入詐騙集團案"
        result = self.extractor.extract(title)
        kws = {kw for kw, _ in result}
        self.assertNotIn("快訊", kws)
        self.assertNotIn("網友", kws)

    def test_top_k_caps_output(self):
        title = "詐騙集團車手被警方逮捕送辦案件擴大偵查"
        result = self.extractor.extract(title, top_k=2)
        self.assertLessEqual(len(result), 2)

    def test_min_keyword_length_filters_singles(self):
        # 預設 min_keyword_length=2，單字（如「人」「他」）不應出現
        title = "他在台北街頭遭人持刀攻擊送醫"
        result = self.extractor.extract(title)
        for kw, _ in result:
            self.assertGreaterEqual(len(kw), 2)

    def test_repeated_calls_share_initialized_state(self):
        # 第二次呼叫不該重複初始化（不會炸，速度快）
        first = self.extractor.extract("台中發生重大車禍")
        second = self.extractor.extract("台中發生重大車禍")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
