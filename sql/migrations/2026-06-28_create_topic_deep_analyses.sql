-- Migration: create topic-level deep-analysis article storage.
-- Run against the news_platform database.
-- Keeps professional issue analysis separate from news articles, barrage, and
-- short-lived relay events.

CREATE TABLE IF NOT EXISTS `t_topic_deep_analyses` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `analysis_uid` VARCHAR(128) NOT NULL,
  `category` VARCHAR(32) NOT NULL,
  `topic_id` VARCHAR(128) NOT NULL,
  `analysis_type` VARCHAR(32) NOT NULL DEFAULT 'root_cause',
  `title` VARCHAR(255) NOT NULL,
  `summary` TEXT NULL,
  `body_markdown` MEDIUMTEXT NOT NULL,
  `root_causes_json` JSON NULL,
  `taiwan_data_json` JSON NULL,
  `international_comparisons_json` JSON NULL,
  `policy_options_json` JSON NULL,
  `limitations_json` JSON NULL,
  `status` VARCHAR(24) NOT NULL DEFAULT 'draft',
  `origin` VARCHAR(32) NOT NULL DEFAULT 'model_generated',
  `author_type` VARCHAR(32) NOT NULL DEFAULT 'model',
  `author_user_id` BIGINT NULL,
  `author_display_name` VARCHAR(120) NULL,
  `model_name` VARCHAR(120) NULL,
  `prompt_version` VARCHAR(80) NULL,
  `generation_run_id` VARCHAR(120) NULL,
  `source_window_start` DATETIME NULL,
  `source_window_end` DATETIME NULL,
  `source_count` INT NOT NULL DEFAULT 0,
  `submitted_at` DATETIME NULL,
  `reviewed_by_user_id` BIGINT NULL,
  `reviewed_at` DATETIME NULL,
  `published_at` DATETIME NULL,
  `metadata_json` JSON NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_topic_deep_analysis_uid` (`analysis_uid`),
  KEY `idx_topic_deep_latest` (`category`, `topic_id`, `analysis_type`, `status`, `published_at`, `id`),
  KEY `idx_topic_deep_status_origin` (`status`, `origin`, `created_at`),
  KEY `idx_topic_deep_author` (`author_type`, `author_user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `t_topic_deep_analysis_sources` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `analysis_id` BIGINT NOT NULL,
  `source_type` VARCHAR(32) NOT NULL,
  `source_ref_table` VARCHAR(80) NULL,
  `source_ref_id` VARCHAR(128) NULL,
  `source_title` VARCHAR(255) NULL,
  `source_url` TEXT NULL,
  `publisher` VARCHAR(128) NULL,
  `country_code` VARCHAR(16) NULL,
  `metric_name` VARCHAR(128) NULL,
  `metric_value_decimal` DECIMAL(20,6) NULL,
  `metric_value_text` VARCHAR(120) NULL,
  `metric_unit` VARCHAR(64) NULL,
  `metric_period` VARCHAR(64) NULL,
  `evidence_role` VARCHAR(40) NOT NULL DEFAULT 'news_context',
  `evidence_note` VARCHAR(512) NULL,
  `raw_json` JSON NULL,
  `published_at` DATETIME NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_topic_deep_sources_analysis` (`analysis_id`, `evidence_role`, `id`),
  KEY `idx_topic_deep_sources_ref` (`source_type`, `source_ref_table`, `source_ref_id`),
  KEY `idx_topic_deep_sources_country` (`country_code`, `evidence_role`, `metric_name`),
  CONSTRAINT `fk_topic_deep_sources_analysis`
    FOREIGN KEY (`analysis_id`) REFERENCES `t_topic_deep_analyses` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
