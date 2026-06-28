CREATE DATABASE IF NOT EXISTS `news_relay` CHARACTER SET utf8mb4;
USE `news_relay`;

CREATE TABLE IF NOT EXISTS `t_relay_events` (
  id BIGINT NOT NULL AUTO_INCREMENT,
  event_id VARCHAR(128) NULL,
  source VARCHAR(64) NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  summary TEXT NULL,
  published_at VARCHAR(64) NULL,
  event_hash CHAR(40) NOT NULL,
  raw_json JSON NULL,
  is_pushed TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_event_hash (event_hash),
  KEY idx_push_queue (is_pushed, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `t_palestine_news_items` (
  id BIGINT NOT NULL AUTO_INCREMENT,
  news_id VARCHAR(128) NOT NULL,
  source_id VARCHAR(64) NOT NULL,
  source_name VARCHAR(128) NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  url_hash CHAR(40) NOT NULL,
  summary TEXT NULL,
  published_at VARCHAR(64) NULL,
  language VARCHAR(16) NOT NULL DEFAULT 'en',
  topic VARCHAR(64) NOT NULL DEFAULT 'free_palestine',
  source_url TEXT NULL,
  original_source VARCHAR(255) NULL,
  original_id VARCHAR(255) NULL,
  tags_json JSON NULL,
  raw_json JSON NULL,
  first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_palestine_news_hash (url_hash),
  KEY idx_palestine_news_published (published_at),
  KEY idx_palestine_news_source (source_id),
  KEY idx_palestine_news_seen (last_seen_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `t_macro_release_calendar` (
  id BIGINT NOT NULL AUTO_INCREMENT,
  event_key CHAR(40) NOT NULL,
  source_id VARCHAR(64) NOT NULL,
  source_name VARCHAR(128) NOT NULL,
  indicator_code VARCHAR(64) NOT NULL,
  indicator_name VARCHAR(128) NOT NULL,
  period_label VARCHAR(64) NOT NULL,
  release_title TEXT NOT NULL,
  release_at_utc DATETIME NOT NULL,
  release_at_taipei DATETIME NOT NULL,
  release_timezone VARCHAR(64) NOT NULL DEFAULT 'America/New_York',
  importance TINYINT NOT NULL DEFAULT 3,
  reminder_date_taipei DATE NOT NULL,
  reminder_pushed TINYINT(1) NOT NULL DEFAULT 0,
  reminder_pushed_at DATETIME NULL,
  reminder_push_status VARCHAR(32) NULL,
  reminder_push_error TEXT NULL,
  source_url TEXT NOT NULL,
  raw_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_macro_release_event_key (event_key),
  KEY idx_macro_release_reminder (reminder_date_taipei, reminder_pushed),
  KEY idx_macro_release_time (release_at_taipei),
  KEY idx_macro_release_indicator (indicator_code, release_at_taipei)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `t_bot_group_info` (
  id BIGINT NOT NULL AUTO_INCREMENT,
  group_id VARCHAR(128) NOT NULL,
  test_account TINYINT(1) NOT NULL DEFAULT 0,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_group_id (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `t_bot_user_info` (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id VARCHAR(128) NOT NULL,
  test_account TINYINT(1) NOT NULL DEFAULT 0,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `t_trade_signals` (
  id BIGINT NOT NULL AUTO_INCREMENT,
  signal_key VARCHAR(64) NOT NULL,
  idempotency_key CHAR(40) NOT NULL,
  analysis_id BIGINT NOT NULL,
  analysis_date VARCHAR(16) NOT NULL,
  analysis_slot VARCHAR(32) NOT NULL,
  market VARCHAR(16) NOT NULL DEFAULT 'TW',
  ticker VARCHAR(32) NOT NULL,
  name VARCHAR(128) NULL,
  signal_type VARCHAR(32) NOT NULL DEFAULT 'analysis_stock_watch',
  strategy_type VARCHAR(32) NOT NULL DEFAULT 'watch',
  direction VARCHAR(16) NOT NULL,
  confidence VARCHAR(16) NULL,
  entry_zone JSON NULL,
  invalidation JSON NULL,
  take_profit_zone JSON NULL,
  holding_horizon VARCHAR(64) NULL,
  rationale TEXT NULL,
  risk_notes JSON NULL,
  source_event_ids JSON NULL,
  risk_reward_ratio DECIMAL(10,4) NULL,
  candidate_score DECIMAL(10,4) NULL,
  avoid_reason TEXT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'pending_review',
  raw_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_trade_signal_key (signal_key),
  UNIQUE KEY uq_trade_signal_idempotency (idempotency_key),
  KEY idx_trade_signal_analysis (analysis_id),
  KEY idx_trade_signal_ticker (market, ticker, status, created_at),
  KEY idx_trade_signal_slot (analysis_date, analysis_slot, status),
  KEY idx_trade_signal_candidate_rank (analysis_date, analysis_slot, status, candidate_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
