# Political Topic And Event Thread Technical Plan

## Purpose

This plan defines the second-layer `politics` topic IDs and the event-thread
model for Taiwan politics news in `data-collecting`.

The goal is to let a repo Codex/sub-agent implement politics classification
without redesigning the whole topic system. Stable politics topics should remain
small and durable; short-lived or evolving events should be represented as
threads under those topics.

## Current State

- `src/news_platform` already collects `category=politics` articles.
- `src/news_platform/registry.py` already stores source metadata such as
  `political_camp` and `china_alignment`.
- `src/news_platform/topics.py` currently contains mostly social/policy issue
  topics plus `general_politics_news`.
- `topics_json` is the current public API surface for article classification.
- `t_public_records` already stores Legislative Yuan bills as
  `category=politics`, `record_type=legislative_bill`.

## Vocabulary

| Field | Meaning | Stability |
|---|---|---|
| `category` | Source section, currently `society` or `politics`. | Stable, source-level |
| `topic_id` | Durable second-layer issue bucket. | Stable, product-level |
| `thread_id` | Specific ongoing event, election cycle, policy cycle, scandal, or diplomatic sequence. | Dynamic |
| `actors` | People, parties, institutions, governments, or campaigns involved. | Dynamic |
| `geo_scope` | Region/country scope such as `TW`, `US`, `CN`, `JP`, `EU`. | Dynamic |
| `event_type` | Thread shape such as `election_cycle`, `diplomatic_visit`, `legislative_session`, `investigation`. | Dynamic |

Do not create a permanent `topic_id` for a single person, one trip, one scandal,
or one election. Those belong to `thread_id`.

## Stable Second-Layer Politics Topics

These IDs are the initial politics topic catalog. They should be implemented as
`TopicSpec` rows that are scoped to `category=politics`.

| topic_id | Label | What belongs here |
|---|---|---|
| `elections` | 選舉與民調 | Presidential, legislative, local, by-election, recall, referendum, nomination, campaign, polling, vote counting. |
| `cross_strait_relations` | 兩岸與台海 | Taiwan-China relations, TAO/MAC, one-China framing, military pressure around Taiwan, cross-strait talks, Taiwan participation disputes framed by China. |
| `foreign_affairs` | 外交與國際政治 | Taiwan diplomacy, US-China or international leader meetings, foreign delegations, APEC/G7/UN/WHO/WHA, allies, sanctions, representative offices. |
| `legislative_policy` | 立法院與政策法案 | Legislative Yuan procedure, bills, amendments, caucus negotiation, committee review, interpellation, Executive Yuan policy packages. |
| `party_politics` | 政黨攻防 | DPP/KMT/TPP party positions, factional conflict, chair elections, caucus statements, party discipline, party-versus-party attacks. |
| `political_accountability` | 政治責任與爭議 | Corruption, conflict of interest, impeachment, Control Yuan correction, resignation calls, official misconduct, investigation of public officials. |
| `defense_security` | 國防與國安 | Defense policy, military procurement, conscription, national security law, intelligence, cyber security, PLA activity when framed as defense/security. |
| `public_budget` | 預算與公共資源 | Central/local budget, special budget, subsidies, fiscal discipline, public construction allocations, budget freezes/cuts. |

## Seed Rule Terms

The first implementation should start conservative. Add terms only when they
improve precision on real recent politics articles.

### `elections`

- Primary: `選舉`, `大選`, `總統大選`, `立委選舉`, `地方選舉`, `補選`, `罷免`, `公投`, `初選`, `提名`, `候選人`, `民調`, `開票`, `選戰`
- Supporting: `選區`, `票倉`, `選民`, `競選`, `政見`, `藍營`, `綠營`, `白營`, `民進黨`, `國民黨`, `民眾黨`
- Exclude: `公司董事選舉`, `工會選舉`, `學生會選舉`

### `cross_strait_relations`

- Primary: `兩岸`, `台海`, `國台辦`, `陸委會`, `九二共識`, `一中原則`, `台獨`, `統一`, `對台`, `共軍`, `解放軍`, `軍演`, `海警`, `M503`
- Supporting: `中國`, `北京`, `福建`, `上海`, `交流`, `ECFA`, `服貿`, `小三通`, `賴清德`, `馬英九`
- Exclude: `中國信託`, `中國鋼鐵`, `中國醫藥大學`

### `foreign_affairs`

- Primary: `外交`, `外交部`, `訪台`, `訪中`, `出訪`, `外賓`, `國是訪問`, `APEC`, `G7`, `聯合國`, `WHO`, `WHA`, `邦交`, `斷交`, `代表處`, `大使`
- Supporting: `台美`, `美中`, `台日`, `日台`, `歐盟`, `制裁`, `峰會`, `川普`, `拜登`, `習近平`
- Exclude: `藝人訪台`, `觀光`, `旅遊`

### `legislative_policy`

- Primary: `立法院`, `立委`, `法案`, `修法`, `草案`, `三讀`, `二讀`, `一讀`, `委員會`, `黨團協商`, `朝野協商`, `院會`, `質詢`
- Supporting: `行政院`, `部會`, `預算案`, `審查`, `條例`, `法律`, `公聽會`, `覆議`
- Exclude: `地方法院`, `法院判決`

### `party_politics`

- Primary: `民進黨`, `國民黨`, `民眾黨`, `時代力量`, `黨主席`, `黨團`, `黨內`, `派系`, `中常會`, `中評會`, `開除黨籍`
- Supporting: `藍營`, `綠營`, `白營`, `政黨`, `黨部`, `互批`, `回嗆`, `砲轟`, `提名`
- Exclude: `黨參`, `黨蔘`

### `political_accountability`

- Primary: `彈劾`, `糾正`, `監察院`, `貪污`, `收賄`, `圖利`, `利益衝突`, `政治獻金`, `官商勾結`, `下台`, `請辭`, `辭職`
- Supporting: `調查`, `檢調`, `廉政署`, `約談`, `搜索`, `起訴`, `道歉`, `爭議`, `公職`
- Exclude: `一般詐騙`, `民事糾紛`

### `defense_security`

- Primary: `國防`, `國安`, `國安會`, `國防部`, `軍購`, `軍演`, `國軍`, `軍機`, `軍艦`, `飛彈`, `防空`, `後備`, `兵役`, `義務役`, `漢光`, `情報`, `間諜`, `共諜`, `資安`, `網攻`
- Supporting: `美國軍售`, `台海`, `共軍`, `解放軍`, `國安法`, `灰色地帶`, `認知作戰`
- Exclude: `一般手機資安`, `企業資安`

### `public_budget`

- Primary: `預算`, `特別預算`, `總預算`, `追加預算`, `凍結預算`, `刪減預算`, `補助`, `統籌分配款`, `財政紀律`, `舉債`, `歲出`, `歲入`
- Supporting: `行政院`, `立法院`, `地方政府`, `國發會`, `主計總處`, `建設經費`, `審查`
- Exclude: `公司預算`, `家庭預算`

## Required Classifier Change

The classifier must become category-aware before politics topics are added.
Otherwise political terms can classify unrelated society rows.

Recommended implementation:

1. Add `categories: tuple[str, ...] = ()` to `TopicSpec`.
2. Add `category: str | None = None` to `topic_classifier.classify`.
3. In `classify`, skip a spec when `spec.categories` is non-empty and the
   normalized article category is not in that set.
4. Update `TopicWorker` to pass `row.category`.
5. Set the eight politics topic specs to `categories=("politics",)`.
6. Keep existing social topics unscoped or explicitly scope them after verifying
   there is no cross-category regression.

## Thread Model

Event threads are dynamic overlays under stable topics. Use them for cases such
as a leader visit, election cycle, major bill package, budget fight, scandal, or
cross-strait incident.

MVP storage uses extra fields in the existing `topics_json` object:

```json
[
  {
    "topic_id": "foreign_affairs",
    "label": "外交與國際政治",
    "score": 1.6,
    "source": "rule",
    "topic_layer": "politics_l2",
    "thread_id": "trump_china_visit_2026",
    "thread_label": "川普訪中",
    "thread_source": "manual_template",
    "event_type": "diplomatic_visit",
    "geo_scope": ["US", "CN", "TW"],
    "actors": ["Donald Trump", "China", "Taiwan"],
    "institutions": ["MOFA", "White House"],
    "confidence": 0.82
  }
]
```

Rules:

- Keep `topic_id` stable and broad.
- Keep `thread_id` lowercase snake_case.
- Prefer `thread_id` values that include a year or election cycle when the
  event is time-bounded.
- Do not overwrite the article's source `category`.
- Do not require thread assignment for every politics article.
- Use thread confidence lower than topic confidence when evidence is partial.

## Thread Template

The reusable template lives at:

- `spec/political-event-threads/_template.md`

Copy it to:

```text
spec/political-event-threads/<thread_id>.md
```

Example thread IDs:

- `trump_china_visit_2026`
- `taiwan_2026_local_election`
- `taipei_mayor_2026_election`
- `defense_special_budget_2026`
- `constitutional_court_law_amendment_2026`

## Sub-Agent Implementation Plan

Give a repo Codex/sub-agent this task:

```text
In D:/work_space/stock/data-collecting, implement the politics second-layer
topic plan in spec/political-topic-thread-technical-plan.md.

Scope:
1. Make TopicSpec and topic_classifier category-aware.
2. Pass article category from TopicWorker into classify.
3. Add the eight politics TopicSpec entries with categories=("politics",).
4. Add tests for each new politics topic and at least two category-scope false
   positive cases.
5. Do not implement full persistent thread tables yet. If adding one sample
   thread, use topics_json extra fields and add a matching test.
6. Update docs if runtime behavior changes.

Verification:
$env:PYTHONPATH='src'
python -m unittest tests.test_news_platform_topic_classifier -v
python -m unittest tests.test_news_platform_topic_worker -v
python scripts/validate_readiness.py
```

## Future Schema Option

If thread queries become frequent, add normalized tables while keeping
`topics_json` as a snapshot:

```sql
CREATE TABLE t_political_threads (
  thread_id VARCHAR(128) PRIMARY KEY,
  topic_id VARCHAR(64) NOT NULL,
  label VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL,
  event_type VARCHAR(64) NULL,
  geo_scope_json JSON NULL,
  actors_json JSON NULL,
  institutions_json JSON NULL,
  keywords_json JSON NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE t_news_article_threads (
  article_id VARCHAR(255) NOT NULL,
  thread_id VARCHAR(128) NOT NULL,
  confidence DECIMAL(5,4) NOT NULL,
  matched_by VARCHAR(64) NOT NULL,
  evidence_json JSON NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (article_id, thread_id)
);
```

Do not add these tables until the frontend/API has real thread list, thread
timeline, or thread media-behavior needs.
