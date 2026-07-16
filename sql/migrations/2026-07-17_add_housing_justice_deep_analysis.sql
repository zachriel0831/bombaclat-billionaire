-- Add the first published root-cause analysis for society / housing_justice.
-- Re-runnable: refreshes the article and rebuilds its source list.

SET NAMES utf8mb4;

START TRANSACTION;

INSERT INTO news_platform.t_topic_deep_analyses (
  analysis_uid,
  category,
  topic_id,
  analysis_type,
  title,
  summary,
  body_markdown,
  root_causes_json,
  taiwan_data_json,
  international_comparisons_json,
  policy_options_json,
  limitations_json,
  status,
  origin,
  author_type,
  author_display_name,
  model_name,
  prompt_version,
  generation_run_id,
  source_window_start,
  source_window_end,
  source_count,
  submitted_at,
  reviewed_at,
  published_at,
  metadata_json
) VALUES (
  'topic-deep-society-housing-justice-root-cause-v1',
  'society',
  'housing_justice',
  'root_cause',
  '高房價不是單一房貸問題：居住正義的根因在土地、信用與供給錯位',
  '近一個月平台收錄 52 篇高房價／居住正義相關新聞，焦點集中在青安 3.0、房貸負擔、租屋透明與社宅輪候。台北市住宅價格指數資料顯示，2026 年 2 月全市住宅月指數為 126.81，標準總價約 2009 萬元；政策若只放寬貸款條件，容易把購屋門檻轉成更長期的家庭負債，而沒有處理土地、租屋與社宅供給的結構缺口。',
  '## 一句話

高房價不是年輕人不努力，也不是房貸方案設計得不夠漂亮，而是土地稀缺、信用擴張、租屋市場不透明與社宅供給不足一起堆出的結構性壓力。

## 目前訊號

平台近一個月收錄 52 篇高房價／居住正義相關新聞，最新討論集中在青安 3.0、排富條款、房貸年限、轉租限制與社宅輪候。媒體熱點顯示，社會討論正在從買不起房，轉向即使貸得到，也可能把一個家庭綁進更長的負債週期。

台北市公開住宅價格指數也提供了背景：2026 年 2 月全市住宅月指數為 126.81，標準總價約 2009 萬元，標準單價每坪約 63.98 萬元；大樓住宅標準總價更接近 2896 萬元。這些數字說明，問題不是單一利率或單一補貼能解決。

## 根因一：信用政策會先進入價格，而不是先進入居住安全

當政府用貸款年限、利息補貼或寬限期降低眼前月付壓力，市場最先反應的往往不是居住品質改善，而是買方可承受價格上升。對已有資產者來說，寬鬆信用提高流動性；對首購者來說，它只是把總價壓力拆成更長的還款期間。若供給與投機管理沒有同步，補貼容易變成價格的支撐，而不是居住權的保障。

## 根因二：租屋市場太弱，讓買房被迫成為唯一安全選項

居住正義不能只談買房。台灣租屋市場長期存在資訊不透明、租約不穩、租金支出難以完整反映、弱勢家庭選擇少等問題。當租屋不能提供可預期的生活安全，人們就會被迫把買房視為唯一出路；而一旦所有人都被推向購屋市場，房價壓力又回頭惡化。

## 根因三：社宅與可負擔住宅供給仍跟不上城市需求

社宅、租金補貼與包租代管能緩解壓力，但若規模不足、輪候時間過長，效果就會停留在補破網。真正的政策重點應是穩定增加可負擔住宅供給，並把交通、就業與公共服務一起納入規劃。居住不是只有一間房，而是能不能在合理通勤、合理支出與可預期生活之間取得平衡。

## 國際比較

OECD 的可負擔住宅資料庫把房價所得比、租金負擔、社會住宅與住房補貼放在同一個框架觀察，提醒我們：住房政策不是單點補貼，而是稅制、金融監理、租屋保障與公共住宅的組合。新加坡、韓國、日本等經驗也顯示，若只刺激購屋需求，難以扭轉長期高房價；較有效的方向通常是提高公共或準公共供給、抑制短期投機、強化租屋權利。

## 政策方向

短期要避免讓青安或類似方案變成推升總價的燃料，因此應搭配嚴格自住、轉租與人頭戶查核。中期要把租屋透明化、租金資料、租賃保障與稅制誘因補齊，讓不買房也能安心生活。長期則要把社宅、可負擔住宅與都市更新連在一起，讓供給真的進入需求集中的地方。

## 風險與資料缺口

目前平台有台北市住宅價格指數與近期新聞脈絡，但全國分區房價、租金負擔率、家庭所得分位與社宅輪候資料仍需要持續補強。因此這篇分析的信心集中在問題結構與政策方向，對各縣市精準量化仍需更多官方資料。',
  JSON_ARRAY(
    JSON_OBJECT('id', 'credit_policy_price_feedback', 'label', '信用寬鬆先進入價格', 'description', '貸款補貼與寬限期若沒有搭配供給與投機管理，容易支撐總價。'),
    JSON_OBJECT('id', 'weak_rental_market', 'label', '租屋市場安全感不足', 'description', '租約不穩、資訊不透明與保障不足，使買房被迫成為唯一安全選項。'),
    JSON_OBJECT('id', 'affordable_supply_gap', 'label', '可負擔供給缺口', 'description', '社宅與可負擔住宅供給規模不足，難以承接都市核心需求。')
  ),
  JSON_OBJECT(
    'news_count', 52,
    'news_window', JSON_OBJECT('start', '2026-06-17', 'end', '2026-07-16'),
    'source_distribution', JSON_OBJECT('storm', 29, 'ettoday', 7, 'cna', 5, 'ltn', 4, 'tvbs', 3, 'newtalk', 2, 'ctee', 1, 'ebc', 1),
    'taipei_home_price_index_2026_02', JSON_OBJECT('monthly_index', 126.81, 'standard_total_price_10k_twd', 2009, 'standard_unit_price_10k_twd_per_ping', 63.98),
    'taipei_building_price_index_2026_02', JSON_OBJECT('monthly_index', 138.59, 'standard_total_price_10k_twd', 2896, 'standard_unit_price_10k_twd_per_ping', 81.12)
  ),
  JSON_ARRAY(
    JSON_OBJECT('country', 'INT', 'source', 'OECD Affordable Housing Database', 'note', '以房價所得比、租金負擔、社會住宅與住房補貼作為住房可負擔性比較框架。')
  ),
  JSON_ARRAY(
    JSON_OBJECT('horizon', 'short', 'title', '避免信用補貼轉嫁為房價支撐', 'description', '青安類方案應搭配自住、轉租、人頭戶與投機交易查核。'),
    JSON_OBJECT('horizon', 'medium', 'title', '補齊租屋市場資料與保障', 'description', '強化租金資訊透明、租賃保障、稅制誘因與弱勢租屋支持。'),
    JSON_OBJECT('horizon', 'long', 'title', '擴大可負擔住宅供給', 'description', '把社宅、包租代管、都市更新與交通就業圈一起規劃。')
  ),
  JSON_ARRAY(
    '目前全國分區房價與租金負擔資料尚未完整接入。',
    '社宅輪候、家庭所得分位與購屋負擔率需持續補強。',
    '本文以近期新聞與台北市公開住宅價格指數作為第一版分析基礎。'
  ),
  'published',
  'model_generated',
  'model',
  'Codex',
  'codex',
  'topic-deep-analysis-v1.1',
  'topic-deep-analysis-housing-justice-2026-07-17',
  '2026-06-17 00:00:00',
  '2026-07-16 23:59:59',
  52,
  UTC_TIMESTAMP(),
  UTC_TIMESTAMP(),
  UTC_TIMESTAMP(),
  JSON_OBJECT('language', 'zh-TW', 'version', 1, 'data_basis', 'public_records_and_recent_news')
)
ON DUPLICATE KEY UPDATE
  title = VALUES(title),
  summary = VALUES(summary),
  body_markdown = VALUES(body_markdown),
  root_causes_json = VALUES(root_causes_json),
  taiwan_data_json = VALUES(taiwan_data_json),
  international_comparisons_json = VALUES(international_comparisons_json),
  policy_options_json = VALUES(policy_options_json),
  limitations_json = VALUES(limitations_json),
  status = VALUES(status),
  origin = VALUES(origin),
  author_type = VALUES(author_type),
  author_display_name = VALUES(author_display_name),
  model_name = VALUES(model_name),
  prompt_version = VALUES(prompt_version),
  generation_run_id = VALUES(generation_run_id),
  source_window_start = VALUES(source_window_start),
  source_window_end = VALUES(source_window_end),
  source_count = VALUES(source_count),
  reviewed_at = VALUES(reviewed_at),
  published_at = VALUES(published_at),
  metadata_json = VALUES(metadata_json),
  updated_at = UTC_TIMESTAMP();

SET @housing_analysis_id := (
  SELECT id
  FROM news_platform.t_topic_deep_analyses
  WHERE analysis_uid = 'topic-deep-society-housing-justice-root-cause-v1'
  LIMIT 1
);

DELETE FROM news_platform.t_topic_deep_analysis_sources
WHERE analysis_id = @housing_analysis_id;

INSERT INTO news_platform.t_topic_deep_analysis_sources (
  analysis_id,
  source_type,
  source_ref_table,
  source_ref_id,
  source_title,
  source_url,
  publisher,
  country_code,
  metric_name,
  metric_value_decimal,
  metric_value_text,
  metric_unit,
  metric_period,
  evidence_role,
  evidence_note,
  raw_json,
  published_at
) VALUES
  (
    @housing_analysis_id,
    'public_record',
    't_public_records',
    '203643',
    '2026-02 台北市全市住宅價格月指數',
    'https://data.gov.tw/dataset/121381',
    '台北市政府地政局',
    'TW',
    'taipei_home_price_index',
    126.810000,
    '標準總價 2009 萬元，標準單價每坪 63.98 萬元',
    'index',
    '2026-02',
    'primary_data',
    '台北市全市住宅價格月指數與標準住宅價格。',
    JSON_OBJECT('monthly_index_change_rate', 0.0067, 'quarter_moving_average', 126.21, 'half_year_moving_average', 126.78),
    '2026-02-28 15:59:59'
  ),
  (
    @housing_analysis_id,
    'public_record',
    't_public_records',
    '203645',
    '2026-02 台北市大樓住宅價格月指數',
    'https://data.gov.tw/dataset/121381',
    '台北市政府地政局',
    'TW',
    'taipei_building_price_index',
    138.590000,
    '標準總價 2896 萬元，標準單價每坪 81.12 萬元',
    'index',
    '2026-02',
    'primary_data',
    '大樓住宅價格指數與標準住宅價格，補充都市核心住宅壓力。',
    JSON_OBJECT('standard_total_price_10k_twd', 2896.0, 'standard_unit_price_10k_twd_per_ping', 81.12),
    '2026-02-28 15:59:59'
  ),
  (
    @housing_analysis_id,
    'external_dataset',
    NULL,
    'data.gov.tw-121381',
    '台北市住宅價格指數',
    'https://data.gov.tw/dataset/121381',
    '政府資料開放平台',
    'TW',
    'housing_price_index_dataset',
    NULL,
    NULL,
    NULL,
    'monthly',
    'primary_data',
    '台北市住宅價格指數公開資料集。',
    NULL,
    NULL
  ),
  (
    @housing_analysis_id,
    'external_dataset',
    NULL,
    'oecd-affordable-housing-database',
    'OECD Affordable Housing Database',
    'https://www.oecd.org/en/data/datasets/oecd-affordable-housing-database.html',
    'OECD',
    'INT',
    'housing_affordability_framework',
    NULL,
    NULL,
    NULL,
    NULL,
    'international_comparison',
    '住房可負擔性國際比較框架。',
    NULL,
    NULL
  ),
  (
    @housing_analysis_id,
    'news_article',
    't_news_articles',
    '1793275',
    '曝房貸快60歲才繳完　柯文哲評青安3.0：笨蛋！問題是房價，不是房貸',
    NULL,
    'storm',
    'TW',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'news_context',
    '近期青安 3.0 與房貸負擔討論。',
    NULL,
    '2026-07-16 14:37:10'
  ),
  (
    @housing_analysis_id,
    'news_article',
    't_news_articles',
    '1787201',
    '民眾黨談居住正義　促落實租屋透明、社宅輪候制',
    NULL,
    'cna',
    'TW',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'news_context',
    '租屋透明與社宅輪候制討論。',
    NULL,
    '2026-07-16 09:13:53'
  ),
  (
    @housing_analysis_id,
    'news_article',
    't_news_articles',
    '1785823',
    '青安3.0挨轟助漲房價　白委嘆：年輕人未來恐租房都難',
    NULL,
    'tvbs',
    'TW',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'news_context',
    '政策補貼與推升房價疑慮。',
    NULL,
    '2026-07-16 08:58:06'
  );

COMMIT;
