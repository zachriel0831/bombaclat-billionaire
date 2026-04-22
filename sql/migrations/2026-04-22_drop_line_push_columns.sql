-- Migration: drop LINE push tracking columns from t_relay_events
--
-- Context:
--   Python repo no longer contacts LINE. The three line_push_* columns were
--   populated only by the legacy push pipeline that is now owned by the Java
--   line-relay-service. Java reads t_market_analyses, not t_relay_events.
--
-- Safety:
--   - is_pushed and idx_push_queue are kept: is_pushed is a generic flag that
--     may still be useful as a future push-queue marker.
--   - No code in this repo reads line_pushed_at / line_push_status /
--     line_push_error anymore after 2026-04-22.
--
-- Apply on each MySQL instance that hosts `news_relay`:
--   mysql -h <host> -u <user> -p news_relay < 2026-04-22_drop_line_push_columns.sql

USE `news_relay`;

ALTER TABLE `t_relay_events`
  DROP COLUMN `line_pushed_at`,
  DROP COLUMN `line_push_status`,
  DROP COLUMN `line_push_error`;
