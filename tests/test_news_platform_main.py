"""news_platform.main config tests."""

import os
import unittest

from news_platform.main import DEFAULT_PUBLIC_RECORD_SOURCES, parse_categories, parse_public_sources


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
        self.assertEqual(parse_public_sources("healthcare-bills"), ("ly_healthcare_bills",))
        self.assertEqual(parse_public_sources("public-budget,budget-bills"), ("ly_budget_bills",))
        self.assertEqual(parse_public_sources("165, traffic-a1"), ("npa_fraud_rumors", "npa_traffic_a1"))
        self.assertEqual(
            parse_public_sources("traffic-a2,drunk-driving,blocked-domains,anti-fraud-dashboard"),
            (
                "npa_traffic_a2_stats",
                "npa_drunk_driving_stats",
                "npa_fraud_blocked_domain_stats",
                "npa_fraud_enforcement_stats",
            ),
        )
        self.assertEqual(
            parse_public_sources("healthcare"),
            (
                "ly_healthcare_bills",
                "nhi_hospital_nursing_staff",
                "nhi_hospital_bed_occupancy",
                "mohw_hospital_workforce",
                "mohw_clinic_workforce",
                "mohw_hospital_beds",
                "mohw_nursing_staff_stats",
            ),
        )
        self.assertEqual(
            parse_public_sources("justice,prosecution-disposition-stats,daily-custody"),
            ("moj_prosecution_disposition_stats", "mojac_daily_custody"),
        )
        self.assertEqual(parse_public_sources("housing,housing-price-index"), ("taipei_housing_price_index",))
        self.assertEqual(parse_public_sources("low-birthrate,birth-monthly"), ("ris_birth_monthly_stats",))
        self.assertEqual(parse_public_sources("drug-abuse,drug-case-stats"), ("npa_drug_case_stats",))

    def test_parse_public_sources_defaults_to_all_stable_sources(self):
        self.assertEqual(parse_public_sources(None), DEFAULT_PUBLIC_RECORD_SOURCES)
        self.assertEqual(parse_public_sources("all"), DEFAULT_PUBLIC_RECORD_SOURCES)


if __name__ == "__main__":
    unittest.main()
