"""全球多語系（英/中/日/韓/德/法）財經新聞情緒分析、區域熱度、總經推演與產業利多歸因引擎。"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from stock_intel.config import SECTORS
from stock_intel.models import (
    BenchmarkQuote,
    MacroOutlook,
    MacroThemeSignal,
    NewsItem,
    RegionSentiment,
    SectorOutlook,
    TWMarketInstitutional,
)

# ---- 英文財經情緒詞典 ----
EN_BULLISH: Dict[str, float] = {
    "rally": 1.3, "rallies": 1.3, "surge": 1.5, "surges": 1.5, "soar": 1.5, "soars": 1.5,
    "jump": 1.1, "jumps": 1.1, "gain": 0.9, "gains": 0.9, "record high": 1.6, "all-time high": 1.6,
    "beat": 1.2, "beats": 1.2, "top estimates": 1.4, "strong earnings": 1.5, "raises guidance": 1.6,
    "upgrade": 1.3, "upgraded": 1.3, "outperform": 1.2, "bullish": 1.4, "optimism": 1.1,
    "rate cut": 1.4, "rate cuts": 1.4, "dovish": 1.2, "easing": 1.0, "stimulus": 1.3,
    "soft landing": 1.4, "cooling inflation": 1.4, "disinflation": 1.3, "growth": 0.7,
    "boom": 1.3, "ai boom": 1.5, "expansion": 1.0, "capex increase": 1.4, "demand surges": 1.5,
    "breakthrough": 1.2, "approval": 1.2, "fda approves": 1.6, "deal": 0.7, "rebound": 1.1,
    "resilient": 1.0, "robust": 1.0, "accelerate": 1.0, "profit rises": 1.4, "buyback": 1.1,
    "dividend hike": 1.2, "ceasefire": 1.3, "trade deal": 1.4, "tariff relief": 1.5, "surplus": 1.0,
}

EN_BEARISH: Dict[str, float] = {
    "sell-off": 1.6, "selloff": 1.6, "plunge": 1.6, "plunges": 1.6, "crash": 1.8, "slump": 1.4,
    "tumble": 1.4, "tumbles": 1.4, "drop": 1.0, "drops": 1.0, "fall": 0.9, "falls": 0.9,
    "slide": 1.1, "slides": 1.1, "worst week": 1.6, "worst day": 1.5, "rout": 1.7, "wipeout": 1.7,
    "miss": 1.2, "misses": 1.2, "cuts guidance": 1.6, "warns": 1.2, "warning": 1.2,
    "downgrade": 1.3, "downgraded": 1.3, "bearish": 1.4, "fear": 1.1, "fears": 1.1, "panic": 1.5,
    "recession": 1.6, "stagflation": 1.7, "inflation rises": 1.4, "sticky inflation": 1.4,
    "rate hike": 1.5, "hawkish": 1.3, "higher for longer": 1.3, "yield spikes": 1.4,
    "tariff": 1.2, "tariffs": 1.3, "trade war": 1.6, "sanctions": 1.3, "export ban": 1.5,
    "export control": 1.3, "export permit": 1.1, "blow": 1.2, "layoffs": 1.2, "default": 1.6,
    "bankruptcy": 1.7, "probe": 1.1, "antitrust": 1.2, "lawsuit": 1.0, "war": 1.4, "conflict": 1.2,
    "escalation": 1.4, "slowdown": 1.2, "contraction": 1.4, "bubble": 1.3, "overvalued": 1.2,
    "weak demand": 1.4, "sec probe": 1.6, "accounting": 0.9, "investigation": 1.3, "steps down": 1.3,
    "ousted": 1.5, "outage": 1.1, "outages": 1.1, "disruption": 1.0, "drags": 1.2, "stall": 1.1,
    "2-year low": 1.5, "record low": 1.4, "turbulence": 1.2,
}

# ---- 中文財經情緒詞典 ----
ZH_BULLISH: Dict[str, float] = {
    "大漲": 1.5, "飆漲": 1.6, "勁揚": 1.3, "上漲": 0.9, "反彈": 1.1, "走強": 1.1, "創新高": 1.6,
    "歷史新高": 1.7, "利多": 1.4, "看多": 1.3, "偏多": 1.1, "優於預期": 1.5, "超預期": 1.5,
    "上修": 1.4, "調升": 1.3, "買超": 1.3, "外資回補": 1.4, "營收創高": 1.6, "獲利成長": 1.4,
    "毛利率升": 1.4, "滿載": 1.3, "急單": 1.4, "擴產": 1.2, "資本支出增加": 1.4, "降息": 1.3,
    "鴿派": 1.2, "通膨降溫": 1.4, "軟著陸": 1.4, "受惠": 1.2, "強勁": 1.1, "回溫": 1.1,
    "突破": 1.1, "高股息": 1.0, "配息": 0.8, "訂單": 0.9, "AI需求": 1.4, "停火": 1.3,
}

ZH_BEARISH: Dict[str, float] = {
    "大跌": 1.5, "重挫": 1.6, "暴跌": 1.7, "崩跌": 1.8, "拋售": 1.6, "殺盤": 1.6, "跳水": 1.5,
    "走跌": 1.0, "下挫": 1.2, "止跌": 1.1, "現金為王": 1.4, "利空": 1.4, "看空": 1.3, "偏空": 1.1,
    "不如預期": 1.5, "低於預期": 1.4, "下修": 1.4, "調降": 1.3, "賣超": 1.3, "提款": 1.3,
    "外資大賣": 1.5, "衰退": 1.6, "停滯性通膨": 1.7, "通膨升溫": 1.4, "升息": 1.4, "鷹派": 1.3,
    "關稅": 1.3, "貿易戰": 1.6, "制裁": 1.3, "管制": 1.2, "禁令": 1.4, "裁員": 1.2,
    "違約": 1.6, "破產": 1.7, "泡沫": 1.3, "泡沫破裂": 1.7, "恐慌": 1.5, "避險": 1.1,
    "衝突": 1.3, "戰爭": 1.4, "地緣風險": 1.3, "疲弱": 1.2, "逆風": 1.2, "承壓": 1.1,
    "匯損": 1.1, "庫存過高": 1.3, "一文不值": 1.5, "下台": 1.5, "辭職": 1.2, "卸任": 1.2,
    "調查": 1.2, "醜聞": 1.6, "閃崩": 1.7, "跌停": 1.6, "變數": 1.0, "找不到底": 1.4, "破底": 1.4, "擔憂": 1.0,
}

# ---- 日文 / 韓文 / 德文 / 法文 全球財經情緒詞典 ----
INTL_BULLISH: Dict[str, float] = {
    # 日文 (JA)
    "急伸": 1.5, "上昇": 1.1, "最高値": 1.6, "増益": 1.4, "好調": 1.2, "上方修正": 1.5,
    "反発": 1.2, "利下げ": 1.3, "成長": 0.9, "買い": 0.9,
    # 韓文 (KO)
    "급등": 1.5, "상승": 1.1, "최고치": 1.6, "호조": 1.3, "흑자": 1.2, "금리 인하": 1.4,
    "반등": 1.2, "강세": 1.2, "수출 증가": 1.3, "실적 개선": 1.4,
    # 德文 (DE)
    "steigt": 1.2, "legt zu": 1.2, "rekordhoch": 1.6, "gewinn": 1.1, "wachstum": 1.0,
    "zinssenkung": 1.4, "aufschwung": 1.3, "erholung": 1.1, "befreiungsschlag": 1.3,
    # 法文 (FR)
    "hausse": 1.2, "bondit": 1.5, "record": 1.2, "croissance": 1.0, "rebond": 1.2,
    "bénéfice": 1.1, "baisse des taux": 1.4, "reprise": 1.1,
}

INTL_BEARISH: Dict[str, float] = {
    # 日文 (JA)
    "急落": 1.6, "下落": 1.2, "暴落": 1.8, "減益": 1.4, "赤字": 1.4, "下方修正": 1.5,
    "懸念": 1.1, "リスク": 1.0, "関税": 1.3, "インフレ": 1.1, "利上げ": 1.3, "売り": 1.0, "低迷": 1.3,
    # 韓文 (KO)
    "급락": 1.6, "하락": 1.2, "폭락": 1.8, "우려": 1.2, "관세": 1.3, "압박": 1.2,
    "위기": 1.5, "적자": 1.4, "둔화": 1.2, "약세": 1.2, "침체": 1.5, "매도": 1.1, "충격": 1.4,
    # 德文 (DE)
    "fällt": 1.2, "stürzt": 1.6, "einbruch": 1.6, "verlust": 1.3, "rezession": 1.6,
    "zölle": 1.3, "krise": 1.5, "inflation": 1.1, "warnung": 1.2, "stellenabbau": 1.3, "risiko": 1.0,
    # 法文 (FR)
    "chute": 1.5, "baisse": 1.1, "plonge": 1.6, "crise": 1.5, "récession": 1.6,
    "droits de douane": 1.4, "inflation": 1.1, "perte": 1.3, "inquiétude": 1.2, "risque": 1.0, "vertigineux": 1.0,
}

# 總經核心主題定義（多語系支援）
MACRO_THEMES: Dict[str, Dict[str, object]] = {
    "ai_capex": {
        "name": "AI 資本支出與科技週期",
        "keywords_en": ["ai ", "artificial intelligence", "gpu", "data center", "nvidia", "hyperscaler", "capex", "openai", "anthropic", "semiconductor", "chip"],
        "keywords_zh": ["AI", "人工智慧", "算力", "半導體", "台積電", "輝達", "資料中心", "伺服器", "資本支出"],
        "keywords_intl": ["半導体", "生成ai", "반도체", "인공지능", "엔비디아", "halbleiter", "ki-", "intelligence artificielle"],
    },
    "rate_cut": {
        "name": "全球央行利率與流動性（Fed/ECB/BOJ）",
        "keywords_en": ["fed", "federal reserve", "rate cut", "interest rate", "powell", "treasury yield", "bond yield", "fomc", "ecb", "boj", "bank of england"],
        "keywords_zh": ["聯準會", "Fed", "降息", "升息", "利率", "央行", "美債", "殖利率", "鮑爾", "資金"],
        "keywords_intl": ["日銀", "金利", "금리", "한국은행", "ezb", "zinsen", "banque centrale", "taux"],
    },
    "tariff_risk": {
        "name": "全球關稅與貿易政策摩擦",
        "keywords_en": ["tariff", "tariffs", "trade war", "customs", "export control", "export permit", "sanction", "protectionism", "trade pressure"],
        "keywords_zh": ["關稅", "貿易戰", "出口管制", "制裁", "禁令", "美中", "貿易摩擦"],
        "keywords_intl": ["関税", "貿易", "통상", "관세", "무역", "zölle", "handelskrieg", "droits de douane"],
    },
    "inflation_oil": {
        "name": "通膨壓力與能源價格",
        "keywords_en": ["inflation", "cpi", "pce", "oil price", "crude", "opec", "energy cost", "stagflation", "saudi"],
        "keywords_zh": ["通膨", "CPI", "油價", "原油", "能源", "物價", "停滯性通膨"],
        "keywords_intl": ["インフレ", "原油", "物価", "인플레이션", "물가", "유가", "ölpreis", "pétrole"],
    },
    "recession": {
        "name": "市場風險情緒與衰退憂慮",
        "keywords_en": ["recession", "sell-off", "selloff", "crash", "slowdown", "layoff", "unemployment", "bubble", "worst week", "rout", "2-year low"],
        "keywords_zh": ["衰退", "拋售", "暴跌", "重挫", "止跌", "現金為王", "泡沫", "失業", "恐慌", "賣壓", "股災"],
        "keywords_intl": ["景気後退", "暴落", "침체", "폭락", "위기", "rezession", "krise", "récession"],
    },
    "geopolitics": {
        "name": "地緣政治與供應鏈重組",
        "keywords_en": ["war", "conflict", "missile", "middle east", "nato", "defense", "geopolitical", "summit", "protest", "ukraine", "russia"],
        "keywords_zh": ["地緣", "戰爭", "衝突", "中東", "軍工", "國防", "台海", "制裁", "峰會"],
        "keywords_intl": ["地政学", "防衛", "방산", "전쟁", "rüstung", "krieg", "géopolitique", "guerre"],
    },
    "soft_landing": {
        "name": "企業獲利與景氣韌性",
        "keywords_en": ["earnings", "profit", "gdp", "retail sales", "soft landing", "ipo", "merger", "buyback", "guidance", "surplus"],
        "keywords_zh": ["財報", "獲利", "營收", "GDP", "景氣", "法說", "配息", "併購", "訂單"],
        "keywords_intl": ["決算", "増益", "실적", "수출", "흑자", "gewinn", "quartalszahlen", "résultats"],
    },
}


def _match_word(text_lower: str, kw: str) -> bool:
    kw_l = kw.lower()
    if any(ord(ch) > 127 for ch in kw_l):
        return kw_l in text_lower
    if " " in kw_l or "-" in kw_l:
        return kw_l in text_lower
    return bool(re.search(rf"\b{re.escape(kw_l)}\b", text_lower))


# ---- 消息面具體事件分類規則（合約／併購／官方公告／監管調查／高層危機／地緣衝突）----
EVENT_RULES: List[Dict[str, object]] = [
    {
        "event_type": "合約/訂單/併購利多",
        "polarity": "bull",
        "reason": "企業傳出簽訂重大合約、大單合作或併購定案，強化營收與市占預期",
        "keywords": [
            "contract", "signed", "wins deal", "acquisition", "finalized", "to buy", "merger", "partnership",
            "order backlog", "supply deal", "large order", "合約", "簽約", "大單", "訂單", "併購", "合作案",
            "結盟", "標案", "得標", "受注", "계약", "수주", "vertrag", "contrat",
        ],
    },
    {
        "event_type": "官方核准/政策/勝訴利多",
        "polarity": "bull",
        "reason": "官方公告核准、法院有利判決、降息寬鬆或救市政策出台，形成政策面催化",
        "keywords": [
            "fda approves", "approved", "court victory", "ruling", "subsidy", "stimulus", "rate cut",
            "ban short", "tariff relief", "核准", "通過", "勝訴", "解禁", "補助", "禁空令", "救市", "降息",
            "befreiungsschlag", "richterspruch", "zinssenkung",
        ],
    },
    {
        "event_type": "財報創高/擴產/資金湧入",
        "polarity": "bull",
        "reason": "財報或訂單動能優於預期、資本支出擴張或外資大舉買進",
        "keywords": [
            "beats", "raises guidance", "record high", "fii buying", "strong earnings", "buyback",
            "capex increase", "優於預期", "上修", "連21紅", "創高", "擴產", "滿載", "外資回補", "買超",
            "上方修正", "増益", "실적 개선",
        ],
    },
    {
        "event_type": "監管調查/出口管制/駁回",
        "polarity": "bear",
        "reason": "面臨官方監管調查（SEC/反壟斷）、出口許可受限、關稅壁壘或主管機關駁回",
        "keywords": [
            "sec probe", "investigates", "investigation", "export permit", "export control", "export ban",
            "fda rejects", "rejects", "antitrust", "sanctions", "tariff", "tariffs", "trade war",
            "監管調查", "出口管制", "關稅", "制裁", "禁令", "駁回", "遭查", "통상 압박", "관세", "関税", "zölle",
        ],
    },
    {
        "event_type": "高層動盪/治理/營運中斷",
        "polarity": "bear",
        "reason": "發生高層異動、會計爭議、裁員或系統中斷等公司治理／營運風險事件",
        "keywords": [
            "steps down", "ousted", "accounting", "layoffs", "outage", "outages", "recall", "scandal",
            "下台", "卸任", "趕創辦人", "辭職", "裁員", "停工", "火災", "醜聞", "stellenabbau",
        ],
    },
    {
        "event_type": "IPO破發/財報失利/恐慌拋售",
        "polarity": "bear",
        "reason": "財報／財測失利、指標股或大型 IPO 跳水引發族群連鎖拋售與估值修正",
        "keywords": [
            "crash", "plunges", "sell-off", "selloff", "rout", "worst week", "bear market", "tumbles",
            "cuts guidance", "misses", "bubble", "2-year low", "跳水", "拋售", "崩跌", "暴跌", "重挫",
            "殺盤", "現金為王", "不如預期", "下修", "急落", "暴落", "투매", "급락", "폭락",
        ],
    },
    {
        "event_type": "地緣衝突/航道能源衝擊",
        "polarity": "bear",
        "reason": "地緣衝突升溫或航道／能源供給受威脅，衝擊全球供應鏈並推升避險與軍工能源關注度",
        "keywords": [
            "war", "strikes", "targets", "drone strike", "missile", "conflict", "protest", "red sea",
            "戰爭", "衝突", "飛彈", "遇襲", "中東", "地緣風險", "전쟁", "krieg", "guerre",
        ],
    },
]


def _classify_news_event(item: NewsItem, text: str, text_lower: str, preferred_polarity: str | None = None) -> Tuple[str, str]:
    """辨識新聞是否包含具體消息面事件（合約、官方公告、監管調查、高層異動、拋售、衝突等）。"""
    best_type = ""
    best_reason = ""
    best_hits = 0

    for rule in EVENT_RULES:
        pol = str(rule.get("polarity", ""))
        if preferred_polarity and pol and pol != preferred_polarity:
            continue
        hits = 0
        for kw in rule["keywords"]:  # type: ignore[attr-defined]
            if _match_word(text_lower, str(kw)) or (any(ord(c) > 127 for c in str(kw)) and str(kw) in text):
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_type = str(rule["event_type"])
            best_reason = str(rule["reason"])

    if not best_type and item.is_official:
        return "官方重訊公告", "台灣證交所／公開資訊觀測站正式發布之重大訊息公告"
    return best_type, best_reason


def score_news_items(news_items: List[NewsItem]) -> List[NewsItem]:
    """對全球多語系新聞進行情緒評分、具體消息面事件分類、總經主題歸類與產業標籤標註。"""
    for item in news_items:
        text = f"{item.title} {item.summary}".strip()
        text_lower = text.lower()
        title_lower = item.title.lower()

        bull_score = 0.0
        bear_score = 0.0
        matched_kw: List[str] = []

        for kw, w in EN_BULLISH.items():
            if _match_word(text_lower, kw):
                bull_score += w * (1.4 if _match_word(title_lower, kw) else 1.0)
                matched_kw.append(f"+{kw}")
        for kw, w in EN_BEARISH.items():
            if _match_word(text_lower, kw):
                bear_score += w * (1.4 if _match_word(title_lower, kw) else 1.0)
                matched_kw.append(f"-{kw}")
        for kw, w in ZH_BULLISH.items():
            if kw in text:
                bull_score += w * (1.4 if kw in item.title else 1.0)
                matched_kw.append(f"+{kw}")
        for kw, w in ZH_BEARISH.items():
            if kw in text:
                bear_score += w * (1.4 if kw in item.title else 1.0)
                matched_kw.append(f"-{kw}")
        for kw, w in INTL_BULLISH.items():
            if _match_word(text_lower, kw):
                bull_score += w * (1.4 if _match_word(title_lower, kw) else 1.0)
                matched_kw.append(f"+{kw}")
        for kw, w in INTL_BEARISH.items():
            if _match_word(text_lower, kw):
                bear_score += w * (1.4 if _match_word(title_lower, kw) else 1.0)
                matched_kw.append(f"-{kw}")

        # 具體消息面事件分類：若正負極性已明顯偏向一方，強制匹配同向事件規則避免誤標
        pref_pol: str | None = None
        if bear_score >= bull_score + 0.8:
            pref_pol = "bear"
        elif bull_score >= bear_score + 0.8:
            pref_pol = "bull"

        ev_type, ev_reason = _classify_news_event(item, text, text_lower, preferred_polarity=pref_pol)
        item.event_type = ev_type
        item.event_reason = ev_reason
        if ev_type in ("合約/訂單/併購利多", "官方核准/政策/勝訴利多") and bull_score < 0.8 and bear_score < 1.2:
            bull_score += 1.0
        elif ev_type in ("監管調查/出口管制/駁回", "高層動盪/治理/營運中斷") and bear_score < 1.0 and bull_score < 1.0:
            bear_score += 1.1

        raw_diff = bull_score - bear_score
        score = round(math.tanh(raw_diff / 2.6), 3)
        item.sentiment_score = score
        if score >= 0.35:
            item.sentiment_label = "利多"
        elif score >= 0.12:
            item.sentiment_label = "偏多"
        elif score <= -0.35:
            item.sentiment_label = "利空"
        elif score <= -0.12:
            item.sentiment_label = "偏空"
        else:
            item.sentiment_label = "中性"

        item.matched_keywords = matched_kw[:6]

        # 全球多語系產業歸類
        sec_ids: List[str] = []
        for sec in SECTORS:
            hit = (
                any(_match_word(text_lower, kw) for kw in sec["keywords_en"])
                or any(kw in text for kw in sec["keywords_zh"])
                or any(_match_word(text_lower, kw) for kw in sec.get("keywords_intl", []))
            )
            if hit:
                sec_ids.append(sec["id"])
        item.matched_sectors = sec_ids

        # 總經主題歸類
        themes: List[str] = []
        for tid, cfg in MACRO_THEMES.items():
            hit = (
                any(_match_word(text_lower, kw) for kw in cfg["keywords_en"])
                or any(kw in text for kw in cfg["keywords_zh"])
                or any(_match_word(text_lower, kw) for kw in cfg.get("keywords_intl", []))
            )
            if hit:
                themes.append(tid)
        item.matched_themes = themes

    return news_items


def _build_region_summary(news_items: List[NewsItem]) -> List[RegionSentiment]:
    grouped: Dict[str, List[NewsItem]] = defaultdict(list)
    for n in news_items:
        grouped[n.macro_region].append(n)

    order = ["北美", "歐洲", "日本", "韓國", "亞太新興", "台灣", "中東全球"]
    summary: List[RegionSentiment] = []
    for reg in order:
        arr = grouped.get(reg) or []
        if not arr:
            continue
        avg = round(sum(x.sentiment_score for x in arr) / len(arr) * 100.0, 1)
        direction = "偏多" if avg >= 8 else ("偏空" if avg <= -8 else "中性")
        top_item = max(arr, key=lambda x: abs(x.sentiment_score) + len(x.matched_sectors) * 0.2)
        summary.append(
            RegionSentiment(
                region=reg,
                news_count=len(arr),
                avg_score=avg,
                direction=direction,
                top_headline=top_item.title[:72],
            )
        )
    return summary


def deduce_macro_outlook(
    news_items: List[NewsItem],
    benchmarks: List[BenchmarkQuote],
    tw_institutional: Optional[TWMarketInstitutional] = None,
) -> Tuple[MacroOutlook, Dict[str, float]]:
    """
    綜合全球多語系財經新聞情緒 + 跨市場大盤動能 + VIX/美債風險 + 台股三大法人買賣超，
    推演當前股市整體走向為「利多」或「利空」。
    """
    # 1. 全球新聞加權情緒分數 (-100 ~ +100)
    weighted_sum = 0.0
    total_w = 0.0
    for item in news_items:
        w = item.impact_weight * (1.25 if item.matched_themes else 0.9)
        weighted_sum += item.sentiment_score * w
        total_w += w
    news_sentiment_score = round((weighted_sum / total_w) * 100.0, 1) if total_w > 0 else 0.0

    # 2. 跨市場指數動能分數 (-100 ~ +100)
    equity_scores: List[float] = []
    risk_scores: List[float] = []
    bm_map = {b.symbol: b for b in benchmarks}
    for b in benchmarks:
        blend = b.change_pct_1d * 0.35 + b.change_pct_5d * 0.45 + b.change_pct_1m * 0.20
        if b.invert_sentiment:
            risk_val = max(-100.0, min(100.0, -blend * 10.0))
            if b.symbol == "^VIX":
                if b.price >= 25:
                    risk_val -= 25.0
                elif b.price >= 20:
                    risk_val -= 10.0
                elif b.price <= 15:
                    risk_val += 15.0
            risk_scores.append(max(-100.0, min(100.0, risk_val)))
        elif b.symbol in ("^GSPC", "^IXIC", "^SOX", "^TWII", "^N225", "^GDAXI"):
            eq_val = max(-100.0, min(100.0, blend * 14.0))
            equity_scores.append(eq_val)

    market_momentum_score = round(sum(equity_scores) / len(equity_scores), 1) if equity_scores else 0.0
    risk_index_score = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0.0

    # 3. 總經主題強度
    theme_signals: List[MacroThemeSignal] = []
    theme_intensity: Dict[str, float] = {}
    for tid, cfg in MACRO_THEMES.items():
        related = [n for n in news_items if tid in n.matched_themes]
        count = len(related)
        if count == 0:
            theme_intensity[tid] = 0.0
            continue
        avg_sent = sum(n.sentiment_score for n in related) / count
        freq_factor = min(1.0, count / 12.0)
        score = round(avg_sent * 100.0 * (0.55 + 0.45 * freq_factor), 1)

        if tid in ("recession", "tariff_risk", "geopolitics", "inflation_oil"):
            theme_intensity[tid] = min(1.0, freq_factor * (0.6 + abs(avg_sent))) if avg_sent <= 0.05 else -min(0.6, freq_factor * avg_sent)
        else:
            theme_intensity[tid] = max(-1.0, min(1.0, (avg_sent + 0.15) * freq_factor))

        direction = "利多" if score >= 12 else ("利空" if score <= -12 else "中性")
        top_title = related[0].title[:58]
        theme_signals.append(
            MacroThemeSignal(
                theme_id=tid,
                theme_name=str(cfg["name"]),
                direction=direction,
                score=score,
                news_count=count,
                reasoning=f"全球共追蹤 {count} 則相關情報（代表新聞：「{top_title}」），整體情緒偏向{direction}。",
            )
        )
    theme_signals.sort(key=lambda t: abs(t.score) + t.news_count * 1.4, reverse=True)

    # 4. 綜合大盤多空總分（全球新聞 42% + 跨市場價格動能 33% + 風險/利率 17% + 台股三大法人籌碼 8%）
    if tw_institutional:
        inst_score = max(-100.0, min(100.0, tw_institutional.total_net_billion * 0.25))
        overall_score = round(
            news_sentiment_score * 0.42
            + market_momentum_score * 0.33
            + risk_index_score * 0.17
            + inst_score * 0.08,
            1,
        )
    else:
        overall_score = round(
            news_sentiment_score * 0.45 + market_momentum_score * 0.35 + risk_index_score * 0.20,
            1,
        )
    overall_score = max(-100.0, min(100.0, overall_score))

    if overall_score >= 28:
        stance = "強烈利多"
    elif overall_score >= 10:
        stance = "溫和利多"
    elif overall_score <= -28:
        stance = "警戒利空"
    elif overall_score <= -10:
        stance = "溫和利空"
    else:
        stance = "震盪中性"

    same_dir = (news_sentiment_score * market_momentum_score) >= 0
    confidence = int(
        min(94, max(44, 52 + min(22, len(news_items) * 0.16) + (14 if same_dir else -6) + abs(overall_score) * 0.18))
    )

    bullish_catalysts: List[str] = []
    bearish_risks: List[str] = []

    if tw_institutional:
        if tw_institutional.total_net_billion >= 50:
            bullish_catalysts.append(tw_institutional.summary)
        elif tw_institutional.total_net_billion <= -50:
            bearish_risks.append(tw_institutional.summary)

    for b in benchmarks:
        if not b.invert_sentiment and b.change_pct_5d >= 1.5:
            bullish_catalysts.append(f"{b.name} 近 5 日上漲 {b.change_pct_5d:+.2f}%，顯示資金動能偏多。")
        elif not b.invert_sentiment and b.change_pct_5d <= -1.5:
            bearish_risks.append(f"{b.name} 近 5 日回檔 {b.change_pct_5d:+.2f}%，短線技術面承受賣壓。")
        elif b.symbol == "^VIX" and b.price >= 20:
            bearish_risks.append(f"恐慌指數 VIX 處於 {b.price:.2f} 偏高區間，全球市場波動與避險情緒升溫。")
        elif b.symbol == "^VIX" and b.price < 16:
            bullish_catalysts.append(f"恐慌指數 VIX 維持於 {b.price:.2f} 低檔，市場風險偏好穩定。")

    top_bull_news = sorted([n for n in news_items if n.sentiment_score >= 0.28], key=lambda x: x.sentiment_score, reverse=True)
    top_bear_news = sorted([n for n in news_items if n.sentiment_score <= -0.28], key=lambda x: x.sentiment_score)

    for n in top_bull_news[:3]:
        bullish_catalysts.append(f"[{n.macro_region}・{n.source}] {n.title}")
    for n in top_bear_news[:3]:
        bearish_risks.append(f"[{n.macro_region}・{n.source}] {n.title}")

    if not bullish_catalysts:
        bullish_catalysts.append("全球市場暫無壓倒性單一利多，資金以防禦輪動與基本面績優股為主。")
    if not bearish_risks:
        bearish_risks.append("目前未見系統性恐慌訊號，但仍需留意央行政策與地緣消息波動。")

    if overall_score >= 15:
        action_plan = [
            "多頭環境順勢布局：優先聚焦「產業利多排行前三」且技術面站上月線（MA20）、台股外資／投信買超的強勢龍頭。",
            "參考策略回測訊號：優先挑選 2 年期量化策略勝率高且當前處於「持有偏多」訊號之標的。",
            "風險控管：留意 RSI > 70 過熱標的，避免過度追高，設定 8% 移動停利紀律。",
        ]
    elif overall_score <= -15:
        action_plan = [
            "防禦優先、保留現金彈性：在歐美亞股同步承壓與外資賣超期，降低高估值、高貝塔個股槓桿。",
            "汰弱留強：優先篩選「基本面 A 級以上」且策略回測最大回撤較低之防禦型或投信護盤標的。",
            "等待右側止跌訊號：觀察 VIX 回落、外資由大賣轉買超，以及標普與台股重新站回 MA20 再擴大部位。",
        ]
    else:
        action_plan = [
            "區間震盪選股不選市：大盤多空分歧，資金集中於少數具基本面成長與法人籌碼護盤的利多產業。",
            "採取「基本面打底 + 法人籌碼確認 + 策略回測驗證」三維篩選流程。",
            "每日盤前追蹤歐美收盤、日韓半導體與台股三大法人動向，動態調整美台股部位。",
        ]

    region_summary = _build_region_summary(news_items)
    reg_cnt = len(region_summary)

    bits = []
    for sym, short in (("^GSPC", "標普500"), ("^SOX", "費半"), ("^TWII", "台股加權"), ("^N225", "日經225"), ("^GDAXI", "德股DAX")):
        if sym in bm_map:
            bits.append(f"{short}近5日 {bm_map[sym].change_pct_5d:+.2f}%")
    inst_txt = f"；台股三大法人單日 {tw_institutional.total_net_billion:+.2f} 億元" if tw_institutional else ""

    executive_summary = (
        f"綜合分析橫跨全球 {reg_cnt} 大市場板塊共 {len(news_items)} 則多語系即時財經情報（全球新聞情緒 {news_sentiment_score:+.1f} 分）"
        f"與跨市場行情（{'、'.join(bits[:4]) or '全球主要指數'}{inst_txt}），"
        f"系統判定當前全球股市走向為「{stance}」（綜合多空指數 {overall_score:+.1f} / 信心度 {confidence}%）。"
    )

    outlook = MacroOutlook(
        overall_score=overall_score,
        stance=stance,
        confidence=confidence,
        news_sentiment_score=news_sentiment_score,
        market_momentum_score=market_momentum_score,
        risk_index_score=risk_index_score,
        executive_summary=executive_summary,
        bullish_catalysts=bullish_catalysts[:5],
        bearish_risks=bearish_risks[:5],
        action_plan=action_plan,
        themes=theme_signals[:6],
        benchmarks=benchmarks,
        region_summary=region_summary,
        tw_institutional=tw_institutional,
        analysis_engine="local_quant",
    )
    return outlook, theme_intensity


def rank_sectors(
    news_items: List[NewsItem],
    theme_intensity: Dict[str, float],
    stock_momentum_by_sector: Dict[str, List[float]],
    stock_fundamental_by_sector: Dict[str, List[float]],
) -> List[SectorOutlook]:
    """結合全球多語系產業新聞情緒、總經順風係數與成分股價量動能，挑選出最可能利多的產業。"""
    outlooks: List[SectorOutlook] = []

    for sec in SECTORS:
        sid = sec["id"]
        rel_news = [n for n in news_items if sid in n.matched_sectors]
        n_count = len(rel_news)

        if n_count > 0:
            w_sum = sum(n.sentiment_score * n.impact_weight for n in rel_news)
            w_tot = sum(n.impact_weight for n in rel_news)
            news_score = round((w_sum / w_tot) * 100.0, 1) if w_tot else 0.0
        else:
            news_score = 0.0

        tailwind_raw = 0.0
        drivers: List[str] = []
        risks: List[str] = []
        for tid, sens in sec["macro_sensitivity"].items():
            intensity = theme_intensity.get(tid, 0.0)
            contrib = sens * intensity * 35.0
            tailwind_raw += contrib
            t_name = str(MACRO_THEMES.get(tid, {}).get("name", tid))
            if contrib >= 8.0:
                drivers.append(f"受惠「{t_name}」主題催化（正向敏感度 {sens:+.1f}）")
            elif contrib <= -8.0:
                risks.append(f"易受「{t_name}」逆風干擾（負向敏感度 {sens:+.1f}）")
        macro_tailwind_score = round(max(-100.0, min(100.0, tailwind_raw)), 1)

        mom_list = stock_momentum_by_sector.get(sid) or []
        price_momentum_score = round(max(-100.0, min(100.0, sum(mom_list) / len(mom_list) if mom_list else 0.0)), 1)

        fund_list = stock_fundamental_by_sector.get(sid) or []
        avg_fund = sum(fund_list) / len(fund_list) if fund_list else 55.0

        norm_news = 50.0 + news_score * 0.5
        norm_macro = 50.0 + macro_tailwind_score * 0.5
        norm_mom = 50.0 + price_momentum_score * 0.5
        final_score = round(
            max(5.0, min(98.0, norm_news * 0.30 + norm_macro * 0.25 + norm_mom * 0.25 + avg_fund * 0.20)),
            1,
        )

        if final_score >= 66:
            label = "高度利多"
        elif final_score >= 54:
            label = "溫和利多"
        elif final_score >= 44:
            label = "中性觀察"
        else:
            label = "偏空承壓"

        if price_momentum_score >= 15:
            drivers.append(f"美台代表成分股近期股價動能強勁（動能分數 {price_momentum_score:+.1f}）")
        elif price_momentum_score <= -15:
            risks.append(f"成分股近期技術面偏弱修正（動能分數 {price_momentum_score:+.1f}）")

        if avg_fund >= 68:
            drivers.append(f"產業成分股整體財報基本面紮實（平均基本面 {avg_fund:.1f} 分）")
        elif avg_fund <= 48:
            risks.append(f"產業整體估值偏高或獲利成長趨緩（平均基本面 {avg_fund:.1f} 分）")

        if n_count >= 3 and news_score >= 10:
            drivers.append(f"全球多語系新聞面偏多（共 {n_count} 則相關報導，情緒 {news_score:+.1f}）")
        elif n_count >= 3 and news_score <= -10:
            risks.append(f"全球新聞面利空雜音較多（共 {n_count} 則相關報導，情緒 {news_score:+.1f}）")

        if not drivers:
            drivers.append("具備中長期產業結構需求，靜待催化劑明朗")
        if not risks:
            risks.append("留意大盤系統性回檔與類股輪動節奏")

        def _pack_catalyst(n: NewsItem, default_tag: str) -> Dict[str, object]:
            tag = n.event_type or ("官方重訊公告" if n.is_official else default_tag)
            reason = n.event_reason or (
                "新聞面釋出正向催化訊號，有助推升族群資金關注"
                if n.sentiment_score >= 0
                else "新聞面傳出負面事件衝擊，短線引發族群賣壓與避險"
            )
            return {
                "event_type": tag,
                "reason": reason,
                "title": n.title,
                "summary": n.summary,
                "full_content": n.full_content or n.summary,
                "source": n.source,
                "macro_region": n.macro_region,
                "lang": n.lang,
                "published_at": n.published_at,
                "sentiment_label": n.sentiment_label,
                "sentiment_score": n.sentiment_score,
                "is_official": n.is_official,
                "link": n.link,
            }

        # 具體消息面利多要素（合約、併購、官方核准、勝訴、財報創高等優先排序）
        bull_rel = sorted(
            [n for n in rel_news if n.sentiment_score >= 0.12 or n.event_type in ("合約/訂單/併購利多", "官方核准/政策/勝訴利多", "財報創高/擴產/資金湧入")],
            key=lambda x: (1 if x.is_official else 0, 1 if x.event_type else 0, x.sentiment_score),
            reverse=True,
        )
        # 具體消息面利空要素（監管調查、出口管制、高層動盪、財報失利/拋售、衝突等優先排序）
        bear_rel = sorted(
            [n for n in rel_news if n.sentiment_score <= -0.12 or n.event_type in ("監管調查/出口管制/駁回", "高層動盪/治理/營運中斷", "IPO破發/財報失利/恐慌拋售", "地緣衝突/航道能源衝擊")],
            key=lambda x: (1 if x.is_official else 0, 1 if x.event_type else 0, -x.sentiment_score),
            reverse=True,
        )

        bull_catalysts_news = [_pack_catalyst(n, "新聞面利多") for n in bull_rel[:3]]
        bear_catalysts_news = [_pack_catalyst(n, "新聞面利空") for n in bear_rel[:3]]

        # 合成一句白話「消息面因果總結」解釋為何利多或利空
        if bull_catalysts_news and (final_score >= 50 or (news_score >= 5 and not bear_catalysts_news)):
            b0 = bull_catalysts_news[0]
            news_summary_reason = f"利多主因【{b0['event_type']}】：{b0['reason']}（{b0['macro_region']}・{b0['source']}：「{str(b0['title'])[:48]}」）"
            if bear_catalysts_news:
                r0 = bear_catalysts_news[0]
                news_summary_reason += f"；另須留意【{r0['event_type']}】干擾。"
        elif bear_catalysts_news:
            r0 = bear_catalysts_news[0]
            news_summary_reason = f"利空主因【{r0['event_type']}】：{r0['reason']}（{r0['macro_region']}・{r0['source']}：「{str(r0['title'])[:48]}」）"
            if bull_catalysts_news:
                b0 = bull_catalysts_news[0]
                news_summary_reason += f"；正面緩衝則有【{b0['event_type']}】。"
        elif drivers:
            news_summary_reason = f"消息面暫無重大單一突發公告，主要受總經結構帶動：{drivers[0]}"
        else:
            news_summary_reason = "目前尚無重大官方公告或突發新聞事件，以技術與基本面輪動為主。"

        top_headlines = [
            {
                "title": n.title,
                "source": n.source,
                "macro_region": n.macro_region,
                "event_type": n.event_type,
                "event_reason": n.event_reason,
                "is_official": n.is_official,
                "sentiment_label": n.sentiment_label,
                "sentiment_score": n.sentiment_score,
                "link": n.link,
            }
            for n in sorted(rel_news, key=lambda x: (1 if x.event_type else 0, abs(x.sentiment_score)), reverse=True)[:5]
        ]

        outlooks.append(
            SectorOutlook(
                sector_id=sid,
                name=sec["name"],
                en_name=sec["en_name"],
                description=sec["description"],
                score=final_score,
                outlook_label=label,
                news_score=news_score,
                macro_tailwind_score=macro_tailwind_score,
                price_momentum_score=price_momentum_score,
                news_count=n_count,
                news_summary_reason=news_summary_reason,
                key_drivers=drivers[:3],
                key_risks=risks[:3],
                bullish_catalysts_news=bull_catalysts_news,
                bearish_catalysts_news=bear_catalysts_news,
                top_headlines=top_headlines,
                stock_symbols=[st["symbol"] for st in sec["stocks"]],
            )
        )

    outlooks.sort(key=lambda s: s.score, reverse=True)
    return outlooks


def split_sector_recommendations(sectors: List[SectorOutlook], top_n: int = 4) -> Tuple[List[SectorOutlook], List[SectorOutlook]]:
    """將產業評分拆分為「產業利多／抗跌推薦排行（由高至低）」與「產業利空／警戒避開排行（由重至輕）」。"""
    if not sectors:
        return [], []
    ordered_high = sorted(sectors, key=lambda s: s.score, reverse=True)
    bullish = ordered_high[:top_n]
    bull_ids = {s.sector_id for s in bullish}
    # 利空警戒排行：優先取評分最低且帶有消息面利空壓力之產業，由承壓最重排至最輕
    remaining = [s for s in reversed(ordered_high) if s.sector_id not in bull_ids]
    bearish = remaining[:top_n] if remaining else list(reversed(ordered_high))[:top_n]
    return bullish, bearish
