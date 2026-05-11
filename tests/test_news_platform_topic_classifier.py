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
