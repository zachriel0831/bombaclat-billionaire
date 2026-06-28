"""news_platform.topic_classifier tests."""

import unittest

from news_platform.topic_classifier import classify


class TopicClassifierTests(unittest.TestCase):
    def test_classifies_multiple_topics_by_score(self):
        result = classify(
            title="酒駕撞死行人 法官輕判引民怨",
            summary=None,
            keywords=[],
        )

        self.assertEqual(result[0]["topic_id"], "drunk_driving_accident")
        self.assertEqual(result[0]["score"], 2.3)
        self.assertEqual(result[1]["topic_id"], "judicial_injustice")
        self.assertEqual(result[1]["score"], 1.6)

    def test_uses_keywords_when_title_does_not_match(self):
        result = classify(
            title="警方破獲地下交易",
            summary="嫌犯藏匿大量物品",
            keywords=[{"kw": "毒咖啡包", "score": 1.2}],
        )

        self.assertEqual(result[0]["topic_id"], "drug_abuse")

    def test_classifies_school_drug_manufacturing_case(self):
        result = classify(
            title="理化老師變「絕命毒師」 判7年9月入獄",
            summary=None,
            keywords=[],
            category="society",
        )

        self.assertEqual(result[0]["topic_id"], "drug_abuse")

    def test_classifies_drug_manufacturing_summary_terms(self):
        result = classify(
            title="檢警破獲校園相關案件",
            summary=(
                "桃園市某國中理化老師利用在學校教化學之便，取得製造第三級毒品"
                "「喵喵」的原料及設備工具，協助製毒工廠製造毒品並教授製毒技術。"
            ),
            keywords=[],
            category="society",
        )

        self.assertEqual(result[0]["topic_id"], "drug_abuse")

    def test_classifies_zombie_vape_title(self):
        result = classify(
            title="中國進口原料煉喪屍煙彈 市值5億",
            summary=None,
            keywords=[],
            category="society",
        )

        self.assertEqual(result[0]["topic_id"], "drug_abuse")

    def test_classifies_low_birthrate_policy_variants(self):
        titles = [
            "\u8cf4\u6e05\u5fb7\u9080\u7da0\u59d4\u8ac7\u5c11\u5b50\u5973\u5316\u653f\u7b56 520\u5927\u79ae\u5305",
            "520\u62cb\u88dc\u52a9\u5927\u79ae\u5305\uff1f\u8cf4\u6e05\u5fb7\u9080\u7da0\u59d4\u8ac7\u300c\u5c11\u5b50\u5973\u5316\u5c0d\u7b56\u300d",
            "0\u52306\u6b72\u570b\u5bb6\u4e00\u8d77\u990a\u653f\u7b56\u64ec\u64f4\u5927",
            "\u5152\u5c11TISA\u64ec\u653e\u5bec\u8cc7\u683c",
            "柯志恩率高雄團隊參訪新北公托 侯友宜大讚育兒三箭政策",
        ]

        for title in titles:
            with self.subTest(title=title):
                result = classify(title=title, summary=None, keywords=[])
                self.assertEqual(result[0]["topic_id"], "low_birthrate")

    def test_low_birthrate_does_not_match_generic_cuisheng(self):
        result = classify(
            title="6成鋼構工程來自宜蘭團隊 林國漳拜訪淡江大橋幕後英雄",
            summary="淡江大橋連通，被視為世界級工程，建山機械團隊一手催生。",
            keywords=[],
            category="politics",
        )

        self.assertNotIn("low_birthrate", [item["topic_id"] for item in result])

    def test_judicial_injustice_requires_controversy_not_plain_appeal(self):
        result = classify(
            title="剴剴案社工陳尚潔一審判刑2年 北檢提起上訴",
            summary="法院依過失致死判刑，檢方對無罪及量刑部分提起上訴。",
            keywords=[],
            category="society",
        )

        self.assertNotIn("judicial_injustice", [item["topic_id"] for item in result])

    def test_judicial_injustice_keeps_light_sentence_cases(self):
        result = classify(
            title="剴剴案社工判刑2年 北檢針對偽造文書無罪、量刑過輕上訴",
            summary=None,
            keywords=[],
            category="society",
        )

        self.assertEqual(result[0]["topic_id"], "judicial_injustice")

    def test_healthcare_burden_does_not_match_doctor_gambling_case(self):
        result = classify(
            title="台中榮總醫師淪莊家抽頭 廠商無照上刀一次拿3萬",
            summary="醫療人員涉賭與廠商糾紛，檢方偵辦中。",
            keywords=[],
            category="society",
        )

        self.assertNotIn("healthcare_burden", [item["topic_id"] for item in result])

    def test_healthcare_burden_keeps_nurse_staffing_cases(self):
        result = classify(
            title="三班護病比入法 工會籲速落實別再燃燒護理師",
            summary=None,
            keywords=[],
            category="society",
        )

        self.assertEqual(result[0]["topic_id"], "healthcare_burden")

    def test_ignores_related_link_blocks_in_summary(self):
        result = classify(
            title="\u4e2d\u570b\u7a31\u6309\u300c\u4e00\u4e2d\u539f\u5247\u300d\u8655\u7406\u53f0\u7063\u53c3\u52a0APEC\u6703\u8b70",
            summary="\u672c\u6587\u8aaa\u660eAPEC\u53c3\u6703\u722d\u8b70\u3002 \u5ef6\u4f38\u95b1\u8b80\uff1a \u8cf4\u6e05\u5fb7\u865f\u53ec\u5e9c\u9662\u9ee8\u56e0\u61c9\u5c11\u5b50\u5973\u5316",
            keywords=[],
        )

        self.assertEqual(result, [])

    def test_exclude_can_prevent_borderline_match(self):
        result = classify(
            title="賽車活動發生車禍",
            summary=None,
            keywords=[],
        )

        self.assertEqual(result, [])

    def test_classifies_collision_variants(self):
        titles = [
            "大貨車駕駛低頭撿手機 釀國道4車連撞 人妻夾困亡",
            "台中貨車機車路口猛烈碰撞 29歲男騎士頭部重創亡",
            "板橋婦走斑馬線闖紅燈過馬路 機車閃避不及撞飛",
        ]

        for title in titles:
            with self.subTest(title=title):
                result = classify(title=title, summary=None, keywords=[])
                self.assertEqual(result[0]["topic_id"], "drunk_driving_accident")

    def test_classifies_passenger_fall_with_traffic_context(self):
        result = classify(
            title="未關門就起步害乘客摔落骨折 中壢客運駕駛涉過失判刑",
            summary=None,
            keywords=[],
        )

        self.assertEqual(result[0]["topic_id"], "drunk_driving_accident")

    def test_excludes_driver_license_subsidy(self):
        result = classify(
            title="竹市學生考機車駕照最高補助1800元",
            summary=None,
            keywords=[],
        )

        self.assertEqual(result, [])

    def test_classifies_politics_second_layer_topics_when_category_matches(self):
        cases = [
            ("elections", "總統大選民調出爐 候選人展開競選造勢"),
            ("cross_strait_relations", "陸委會回應國台辦一中原則與兩岸談話"),
            ("foreign_affairs", "外交部說明APEC與WHA參與 友邦訪團抵台"),
            ("legislative_policy", "立法院委員會審查修法草案 行政院提出政策"),
            ("party_politics", "民進黨與民眾黨黨團攻防 黨主席處理黨紀"),
            ("political_accountability", "監察院彈劾涉貪官員 要求不適任首長請辭下台"),
            ("defense_security", "國防部軍購無人機 強化國安與國軍防衛"),
            ("public_budget", "行政院編列特別預算 立法院審查公共建設經費"),
        ]

        for expected_topic_id, title in cases:
            with self.subTest(topic_id=expected_topic_id):
                result = classify(title=title, summary=None, keywords=[], category="politics")
                self.assertEqual(result[0]["topic_id"], expected_topic_id)

    def test_politics_topics_do_not_match_society_rows(self):
        cases = [
            "總統大選民調出爐 候選人展開競選造勢",
            "國防部軍購無人機 強化國安與國軍防衛",
        ]

        for title in cases:
            with self.subTest(title=title):
                result = classify(title=title, summary=None, keywords=[], category="society")
                self.assertEqual(result, [])

    def test_max_topics_limits_output(self):
        result = classify(
            title="酒駕撞死行人 詐騙集團被起訴 房價飆漲",
            summary="法官判決引民怨 投資詐騙與居住正義同受關注",
            keywords=[],
            max_topics=2,
        )

        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
