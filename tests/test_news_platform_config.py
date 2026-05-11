"""news_platform.config tests."""

import os
import tempfile
import unittest
from pathlib import Path

from news_platform.config import load_settings


class NewsPlatformConfigTests(unittest.TestCase):
    def test_public_record_table_names_default_and_override(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "NEWSPF_MYSQL_PUBLIC_RECORD_TABLE=t_custom_records",
                        "NEWSPF_MYSQL_ARTICLE_RECORD_LINK_TABLE=t_custom_links",
                    ]
                ),
                encoding="utf-8",
            )
            keys = [
                "NEWSPF_MYSQL_PUBLIC_RECORD_TABLE",
                "NEWSPF_MYSQL_ARTICLE_RECORD_LINK_TABLE",
            ]
            old = {key: os.environ.get(key) for key in keys}
            for key in keys:
                os.environ.pop(key, None)
            try:
                settings = load_settings(str(env_path))
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(settings.mysql_public_record_table, "t_custom_records")
        self.assertEqual(settings.mysql_article_record_link_table, "t_custom_links")

    def test_public_record_table_names_have_defaults(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text("", encoding="utf-8")
            keys = [
                "NEWSPF_MYSQL_PUBLIC_RECORD_TABLE",
                "NEWSPF_MYSQL_ARTICLE_RECORD_LINK_TABLE",
            ]
            old = {key: os.environ.get(key) for key in keys}
            for key in keys:
                os.environ.pop(key, None)
            try:
                settings = load_settings(str(env_path))
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(settings.mysql_public_record_table, "t_public_records")
        self.assertEqual(
            settings.mysql_article_record_link_table,
            "t_news_article_public_record_links",
        )


if __name__ == "__main__":
    unittest.main()
