-- Migration: create long-term Free Palestine English issue-news storage.
-- Keeps issue news out of short-retention t_relay_events while preserving
-- /api/timeline/news compatibility through news-platform-api.

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
