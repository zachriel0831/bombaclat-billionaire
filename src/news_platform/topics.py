"""Taiwan society topic registry for deterministic article classification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicSpec:
    topic_id: str
    label: str
    primary: tuple[str, ...]
    supporting: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    min_score: float = 1.0


GENERAL_SOCIAL_TOPIC_ID = "general_social_news"
GENERAL_SOCIAL_TOPIC_LABEL = "一般社會新聞"


def general_social_topic(
    *,
    source: str = "rule_fallback",
    reason: str = "no_specific_topic_match",
    score: float = 0.0,
    **extra: object,
) -> dict[str, object]:
    """Return the temporary fallback topic for articles without a specific issue hit."""
    payload: dict[str, object] = {
        "topic_id": GENERAL_SOCIAL_TOPIC_ID,
        "label": GENERAL_SOCIAL_TOPIC_LABEL,
        "score": round(float(score), 2),
        "source": source,
        "reason": reason,
    }
    payload.update(extra)
    return payload


TOPIC_REGISTRY: list[TopicSpec] = [
    TopicSpec(
        topic_id="drunk_driving_accident",
        label="酒駕毒駕／車禍傷亡",
        primary=(
            "酒駕",
            "毒駕",
            "車禍",
            "肇事",
            "肇逃",
            "撞死",
            "撞傷",
            "翻車",
            "追撞",
            "闖紅燈",
            "駕駛肇事",
            "酒測",
            "毒品駕車",
        ),
        supporting=(
            "駕駛",
            "路口",
            "斑馬線",
            "行人",
            "機車",
            "貨車",
            "肇責",
            "超速",
            "闖燈",
            "車禍現場",
            "死亡車禍",
            "重傷",
            "奪命",
        ),
        exclude=(
            "賽車",
            "電動車補貼",
            "停車費",
            "模型車",
            "玩具車",
        ),
    ),
    TopicSpec(
        topic_id="fraud",
        label="詐騙",
        primary=(
            "詐騙",
            "詐欺",
            "假投資",
            "假交友",
            "車手",
            "詐團",
            "詐騙集團",
            "解除分期",
            "假檢察官",
            "一頁式廣告",
            "投資詐騙",
        ),
        supporting=(
            "被騙",
            "投資群組",
            "假冒",
            "簡訊詐",
            "ATM",
            "匯款",
            "遭詐",
            "報案",
            "防詐",
            "識詐",
        ),
        exclude=(
            "電影",
            "小說",
            "詐騙片",
            "劇情",
        ),
    ),
    TopicSpec(
        topic_id="low_birthrate",
        label="少子化",
        primary=(
            "少子化",
            "出生率",
            "生育率",
            "生育補助",
            "育兒津貼",
            "催生",
            "人口負成長",
            "新生兒數",
            "出生人數",
        ),
        supporting=(
            "托育",
            "幼兒園",
            "托嬰",
            "孕婦",
            "新生兒",
            "育嬰假",
            "生育意願",
            "不婚",
            "不生",
            "人口危機",
        ),
        exclude=(
            "移民人口",
            "外籍配偶人數統計",
        ),
    ),
    TopicSpec(
        topic_id="judicial_injustice",
        label="司法量刑不公",
        primary=(
            "量刑",
            "輕判",
            "無罪",
            "司法不公",
            "恐龍法官",
            "司法已死",
            "判決爭議",
            "緩刑爭議",
            "死刑執行",
        ),
        supporting=(
            "法官",
            "檢察官",
            "上訴",
            "緩刑",
            "易科罰金",
            "民怨",
            "判決",
            "起訴",
            "不起訴",
            "輿論譁然",
        ),
        exclude=(
            "民事賠償",
            "離婚訴訟",
            "商業糾紛",
            "勞資爭議",
            "專利訴訟",
        ),
    ),
    TopicSpec(
        topic_id="healthcare_burden",
        label="醫護過勞／醫療崩潰",
        primary=(
            "醫護",
            "護理師",
            "急診壅塞",
            "醫療人力",
            "住院醫師",
            "醫師過勞",
            "護理荒",
            "醫療崩潰",
            "急診人力",
        ),
        supporting=(
            "過勞",
            "罷工",
            "離職潮",
            "輪班",
            "短缺",
            "排班",
            "血汗",
            "缺額",
            "醫療量能",
            "醫護出走",
        ),
        exclude=(
            "護理之家",
            "安養",
            "長照機構",
        ),
    ),
    TopicSpec(
        topic_id="housing_justice",
        label="高房價／居住正義",
        primary=(
            "房價",
            "囤房",
            "房屋稅",
            "社會住宅",
            "租金補貼",
            "炒房",
            "居住正義",
            "房價所得比",
            "買不起房",
        ),
        supporting=(
            "租屋",
            "首購",
            "房貸",
            "建商",
            "預售屋",
            "地價",
            "空屋",
            "包租代管",
            "青年住宅",
        ),
        exclude=(
            "商辦",
            "工業用地",
            "農地買賣",
            "商業不動產",
        ),
    ),
    TopicSpec(
        topic_id="drug_abuse",
        label="新興毒品／校園毒品",
        primary=(
            "新興毒品",
            "校園毒品",
            "毒品濫用",
            "K他命",
            "安非他命",
            "大麻",
            "毒咖啡包",
            "電子煙毒品",
            "販毒",
        ),
        supporting=(
            "吸毒",
            "施用毒品",
            "查獲毒品",
            "毒品交易",
            "緝毒",
            "戒毒",
            "青少年毒品",
            "毒品氾濫",
        ),
        exclude=(
            "毒駕",
            "毒品電影",
        ),
    ),
]
