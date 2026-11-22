"""AI 信用風險雷達引擎：結合全球債市信用利差、槓桿貸款、區域銀行壓力、新聞信用事件與個股五維財報違約壓力模型。"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from stock_intel.collectors.article_reader import extract_article_content
from stock_intel.models import (
    BenchmarkQuote,
    CreditRadarReport,
    NewsItem,
    StockCreditRisk,
    StockReport,
)

# 五維雷達統一座標軸（系統性市場與個股可疊加對比）
RADAR_DIMENSIONS: List[Dict[str, str]] = [
    {"key": "leverage", "label": "財務槓桿壓力", "sys_label": "信用利差與槓桿", "desc": "負債權益比、淨負債/EBITDA 與高收益債利差擴大壓力"},
    {"key": "liquidity", "label": "短期流動性", "sys_label": "利率與再融資", "desc": "流動比率、速動比率、現金/總負債覆蓋與美債利率負擔"},
    {"key": "cashflow", "label": "現金流償債力", "sys_label": "銀行與私募信貸", "desc": "自由現金流利潤率、營業現金流償債能力與槓桿貸款/銀行壓力"},
    {"key": "market_stress", "label": "市場隱含違約", "sys_label": "股市波動違約壓力", "desc": "Merton 風格權益波動率、高點回撤與 VIX 市場隱含壓力"},
    {"key": "event_risk", "label": "AI消息信用風險", "sys_label": "全球信用事件密度", "desc": "違約、降評、私募信貸、AI舉債、監管調查與資金鏈負面情報"},
]

# 全球多語系信用風險事件分類規則（高精準度，避免雜訊誤報）
CREDIT_EVENT_RULES: List[Tuple[str, str, float, Tuple[str, ...]]] = [
    (
        "違約/破產/債務重整",
        "企業或債市傳出違約、破產保護、債務重整或跳票警報，屬最高等級信用風險訊號",
        1.0,
        (
            "default risk", "debt default", "bond default", "bankruptcy", "chapter 11",
            "insolvency", "debt restructuring", "distressed debt", "missed payment",
            "違約", "破產", "債務重整", "跳票", "倒債", "財務危機",
        ),
    ),
    (
        "信評降評/展望負向",
        "國際信評機構（Moody's/S&P/Fitch）下調評等或列入負向觀察，推高企業發債融資成本",
        0.88,
        (
            "credit downgrade", "downgraded", "junk status", "fallen angel",
            "negative outlook", "credit watch", "moody's cut", "fitch cut", "s&p cut",
            "降評", "信評下調", "評等展望負向", "垃圾債",
        ),
    ),
    (
        "AI舉債/高收益利差/私募信貸壓力",
        "高收益債利差擴大、私募信貸或 AI 資本支出大舉舉債引發再融資與償債疑慮",
        0.82,
        (
            "credit spread", "high-yield", "high yield", "junk bond", "private credit",
            "leveraged loan", "debt-laden", "debt-funded", "refinancing wall",
            "corporate debt", "bond sell-off", "credit crunch", "credit stress",
            "公司債利差", "高收益債", "私募信貸", "槓桿貸款", "舉債", "債務壓力", "聯貸",
        ),
    ),
    (
        "流動性緊縮/燒錢/追繳保證金",
        "流動性吃緊、現金消耗過快、違約條款或保證金追繳恐引發連鎖去槓桿",
        0.75,
        (
            "liquidity crunch", "margin call", "cash burn", "covenant breach",
            "liquidity risk", "funding squeeze", "debt pile", "solvency",
            "流動性危機", "資金鏈", "追繳保證金", "斷頭", "燒錢", "現金流吃緊",
        ),
    ),
]


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, val)), 1)


def _risk_level_from_score(score: float) -> str:
    if score >= 68:
        return "高危紅燈"
    if score >= 48:
        return "中度警戒"
    if score >= 30:
        return "留意觀察"
    return "低風險"


def _credit_rating_from_score(score: float) -> str:
    if score < 18:
        return "AAA"
    if score < 28:
        return "AA"
    if score < 38:
        return "A"
    if score < 50:
        return "BBB"
    if score < 62:
        return "BB"
    if score < 76:
        return "B"
    return "CCC"


def _calc_volatility_and_dd(chart: Optional[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
    """計算近 60 交易日年化波動率 (%) 與近一年高點回撤 (%)，作為 Merton 風格市場隱含違約壓力代理。"""
    if not chart:
        return None, None
    bars = chart.get("bars") or []
    closes = [float(b["close"]) for b in bars if b.get("close") and float(b["close"]) > 0]
    if len(closes) < 15:
        return None, None

    recent = closes[-61:]
    rets = [math.log(recent[i] / recent[i - 1]) for i in range(1, len(recent)) if recent[i - 1] > 0]
    if len(rets) >= 10:
        mean_r = sum(rets) / len(rets)
        var = sum((r - mean_r) ** 2 for r in rets) / max(1, len(rets) - 1)
        vol_ann = math.sqrt(var * 252.0) * 100.0
    else:
        vol_ann = None

    peak_252 = max(closes[-252:])
    last = closes[-1]
    dd_pct = ((last - peak_252) / peak_252 * 100.0) if peak_252 > 0 else None
    return (round(vol_ann, 1) if vol_ann is not None else None), (round(dd_pct, 1) if dd_pct is not None else None)


def _detect_credit_event(n: NewsItem) -> Optional[Tuple[str, str, float]]:
    text = f"{n.title} {n.summary}".lower()
    for ev_name, reason, severity, kws in CREDIT_EVENT_RULES:
        if any(kw in text for kw in kws):
            return ev_name, reason, severity
    return None


def analyze_stock_credit_risk(
    symbol: str,
    name: str,
    sector_id: str,
    fundamentals: Dict[str, Any],
    chart: Optional[Dict[str, Any]],
    related_news: List[Dict[str, Any]],
    systemic_spread_stress: float = 40.0,
) -> StockCreditRisk:
    """
    計算單一公司之 AI 信用風險五維雷達評分（0=最安全, 100=最高風險）與模擬信用評等（AAA~CCC）。
    針對金融業（銀行／金控）自動調整負債比權重，避免將銀行存款誤判為高風險負債。
    """
    is_financial = sector_id == "financials"

    dte = fundamentals.get("debt_to_equity")       # Yahoo 通常為百分比 (例如 85.0 代表 0.85x)
    cur_ratio = fundamentals.get("current_ratio")
    quick_ratio = fundamentals.get("quick_ratio")
    total_cash = fundamentals.get("total_cash")
    total_debt = fundamentals.get("total_debt")
    fcf = fundamentals.get("free_cash_flow")
    ocf = fundamentals.get("operating_cash_flow")
    ebitda = fundamentals.get("ebitda")
    total_rev = fundamentals.get("total_revenue")
    profit_margin = fundamentals.get("profit_margin_pct")
    beta = fundamentals.get("beta")

    net_debt = (total_debt - total_cash) if (total_debt is not None and total_cash is not None) else None
    net_debt_to_ebitda: Optional[float] = None
    if net_debt is not None and ebitda is not None and ebitda > 0:
        net_debt_to_ebitda = round(net_debt / ebitda, 2)
    cash_to_debt: Optional[float] = None
    if total_cash is not None and total_debt is not None and total_debt > 0:
        cash_to_debt = round(total_cash / total_debt, 2)
    fcf_margin_pct: Optional[float] = None
    if fcf is not None and total_rev is not None and total_rev > 0:
        fcf_margin_pct = round(fcf / total_rev * 100.0, 1)

    vol_60d, dd_52w = _calc_volatility_and_dd(chart)

    red_flags: List[str] = []
    buffers: List[str] = []

    # ---- 維度 1：財務槓桿壓力 (Leverage Risk) ----
    lev_score = 32.0
    if is_financial:
        # 金融業以獲利韌性、現金覆蓋與輕微槓桿微調替代一般企業 D/E
        lev_score = 36.0
        if dte is not None and dte > 350:
            lev_score += 14.0
            red_flags.append(f"金融槓桿偏高（D/E {dte:.0f}%），須留意利差倒掛與放款呆帳壓力。")
        elif dte is not None and dte < 150:
            lev_score -= 8.0
            buffers.append(f"金融資本結構相對穩健（D/E {dte:.0f}%）。")
    else:
        if dte is not None:
            if dte > 200:
                lev_score = 78.0
                red_flags.append(f"負債權益比高達 {dte:.0f}%，財務槓桿偏重、高利率下再融資成本敏感。")
            elif dte > 120:
                lev_score = 58.0
                red_flags.append(f"負債權益比達 {dte:.0f}%，債務槓桿略高於安全基準。")
            elif dte > 60:
                lev_score = 38.0
            elif dte >= 0:
                lev_score = 18.0
                buffers.append(f"低負債資本結構（D/E 僅 {dte:.0f}%），財務槓桿風險極低。")
        if net_debt_to_ebitda is not None:
            if net_debt_to_ebitda <= 0:
                lev_score = min(lev_score, 14.0)
                buffers.append("帳上現金大於總負債（淨現金狀態），幾乎無淨債務壓力。")
            elif net_debt_to_ebitda > 4.0:
                lev_score = max(lev_score, 80.0)
                red_flags.append(f"淨負債 / EBITDA 達 {net_debt_to_ebitda:.1f} 倍，長期償債期偏長。")
            elif net_debt_to_ebitda > 2.5:
                lev_score = max(lev_score, 58.0)
            elif net_debt_to_ebitda < 1.0:
                lev_score = max(10.0, lev_score - 8.0)

    # ---- 維度 2：短期流動性風險 (Liquidity Risk) ----
    liq_score = 34.0
    if cur_ratio is not None:
        if cur_ratio < 0.85:
            liq_score = 80.0
            red_flags.append(f"流動比率僅 {cur_ratio:.2f} 倍（低於 1.0 警戒線），短期週轉緩衝吃緊。")
        elif cur_ratio < 1.15:
            liq_score = 56.0
            red_flags.append(f"流動比率 {cur_ratio:.2f} 倍偏緊，須追蹤短期應付債務續借狀況。")
        elif cur_ratio >= 2.0:
            liq_score = 15.0
            buffers.append(f"流動比率達 {cur_ratio:.2f} 倍，短期清償能力充裕。")
        else:
            liq_score = 30.0
    if cash_to_debt is not None:
        if cash_to_debt >= 1.0:
            liq_score = max(10.0, liq_score - 12.0)
            if not any("淨現金" in b for b in buffers):
                buffers.append(f"帳上現金可覆蓋總負債 {cash_to_debt:.2f} 倍，流動性護城河深厚。")
        elif cash_to_debt < 0.15 and not is_financial:
            liq_score = min(92.0, liq_score + 18.0)
            red_flags.append(f"現金對總負債覆蓋率僅 {cash_to_debt*100:.0f}%，高度依賴外部融資滾動。")

    # ---- 維度 3：現金流與償債覆蓋風險 (Cashflow & Coverage Risk) ----
    cf_score = 35.0
    if fcf is not None:
        if fcf < 0:
            cf_score = 72.0
            if ocf is not None and ocf < 0:
                cf_score = 86.0
                red_flags.append("營業現金流與自由現金流雙雙為負，持續消耗帳上現金。")
            else:
                red_flags.append("自由現金流為負值（高資本支出或營運現金流出），須留意資本開支與舉債節奏。")
        else:
            cf_score = 22.0
            if fcf_margin_pct is not None and fcf_margin_pct >= 18.0:
                cf_score = 12.0
                buffers.append(f"自由現金流利潤率高達 {fcf_margin_pct:.1f}%，內生造血與還債能力強勁。")
            elif fcf_margin_pct is not None and fcf_margin_pct >= 8.0:
                cf_score = 20.0
                buffers.append(f"自由現金流保持正向（FCF 利潤率 {fcf_margin_pct:.1f}%），償債資金來源穩定。")
            else:
                buffers.append("自由現金流為正，具備正向現金造血能力。")
    if profit_margin is not None:
        if profit_margin < 0:
            cf_score = min(95.0, cf_score + 16.0)
            red_flags.append(f"淨利率為負（{profit_margin:.1f}%），本業獲利承壓削弱利息保障倍數。")
        elif profit_margin >= 20.0:
            cf_score = max(10.0, cf_score - 8.0)

    # ---- 維度 4：市場隱含違約壓力 (Merton Equity Volatility & Drawdown Stress) ----
    mkt_score = 30.0
    if vol_60d is not None:
        if vol_60d >= 60:
            mkt_score = 76.0
            red_flags.append(f"近 60 日年化波動率高達 {vol_60d:.1f}%，權益市場隱含信用波動急劇升溫。")
        elif vol_60d >= 42:
            mkt_score = 56.0
        elif vol_60d >= 26:
            mkt_score = 36.0
        else:
            mkt_score = 18.0
            buffers.append(f"股價年化波動率僅 {vol_60d:.1f}%，市場隱含資產價值穩定。")
    if dd_52w is not None:
        if dd_52w <= -35.0:
            mkt_score = min(95.0, mkt_score + 20.0)
            red_flags.append(f"股價自近一年高點回撤 {dd_52w:.1f}%，權益緩衝墊大幅縮水（Merton 違約距離收窄）。")
        elif dd_52w <= -20.0:
            mkt_score = min(90.0, mkt_score + 10.0)
    if beta is not None and beta > 1.6:
        mkt_score = min(95.0, mkt_score + 6.0)

    # ---- 維度 5：AI 消息面與信用事件風險 (News & Event Credit Risk) ----
    ev_score = 16.0 + systemic_spread_stress * 0.28
    for n in related_news:
        txt = f"{n.get('title', '')} {n.get('summary', '')} {n.get('event_type', '')}".lower()
        sc = float(n.get("sentiment_score") or 0.0)
        if any(k in txt for k in ("default", "bankruptcy", "downgrade", "debt-laden", "probe", "sec ", "margin call", "違約", "降評", "調查", "資金鏈")):
            ev_score += 22.0
            if len(red_flags) < 4:
                red_flags.append(f"消息面偵測負面信用／監管事件：「{str(n.get('title', ''))[:42]}」")
        elif sc <= -0.45:
            ev_score += 10.0
        elif sc >= 0.45:
            ev_score -= 5.0

    dims = {
        "leverage": _clamp(lev_score),
        "liquidity": _clamp(liq_score),
        "cashflow": _clamp(cf_score),
        "market_stress": _clamp(mkt_score),
        "event_risk": _clamp(ev_score),
    }

    risk_score = _clamp(
        dims["leverage"] * 0.25
        + dims["liquidity"] * 0.20
        + dims["cashflow"] * 0.22
        + dims["market_stress"] * 0.20
        + dims["event_risk"] * 0.13
    )
    credit_rating = _credit_rating_from_score(risk_score)
    risk_level = _risk_level_from_score(risk_score)

    if not red_flags:
        red_flags.append("目前財報槓桿與流動性未見顯著違約紅旗，僅須持續追蹤總經利率與大盤波動。")
    if not buffers:
        buffers.append("仍具備上市龍頭資本市場籌資管道，但建議嚴控高槓桿擴張期之現金流紀律。")

    worst_axis_key = max(dims, key=lambda k: dims[k])
    axis_zh = {d["key"]: d["label"] for d in RADAR_DIMENSIONS}.get(worst_axis_key, worst_axis_key)
    ai_diagnosis = (
        f"AI 模擬信評 {credit_rating}（信用風險指數 {risk_score:.1f} / {risk_level}）。"
        f"五維檢測中主要壓力源為「{axis_zh}」（{dims[worst_axis_key]:.0f} 分），"
        + (f"核心警示：{red_flags[0]}" if risk_score >= 45 else f"核心護城河：{buffers[0]}")
    )

    return StockCreditRisk(
        risk_score=risk_score,
        credit_rating=credit_rating,
        risk_level=risk_level,
        dimensions=dims,
        metrics={
            "debt_to_equity": round(dte, 1) if dte is not None else None,
            "net_debt_to_ebitda": net_debt_to_ebitda,
            "cash_to_debt": cash_to_debt,
            "current_ratio": round(cur_ratio, 2) if cur_ratio is not None else None,
            "quick_ratio": round(quick_ratio, 2) if quick_ratio is not None else None,
            "fcf_margin_pct": fcf_margin_pct,
            "volatility_60d_pct": vol_60d,
            "drawdown_52w_pct": dd_52w,
            "beta": round(beta, 2) if beta is not None else None,
        },
        red_flags=red_flags[:4],
        buffers=buffers[:3],
        ai_diagnosis=ai_diagnosis,
    )


def compute_systemic_spread_stress(
    credit_proxies: List[Dict[str, Any]],
    benchmarks: List[BenchmarkQuote],
) -> Tuple[float, Dict[str, Any]]:
    """從 HYG/LQD/IEF/BKLN/KRE、10Y美債殖利率與 VIX 估算市場即時系統性信用利差壓力 (0~100)。"""
    pmap = {p["symbol"]: p for p in credit_proxies}
    bmap = {b.symbol: b for b in benchmarks}

    hyg = pmap.get("HYG")
    lqd = pmap.get("LQD")
    ief = pmap.get("IEF")
    bkln = pmap.get("BKLN")
    kre = pmap.get("KRE")
    tnx = bmap.get("^TNX")
    vix = bmap.get("^VIX")

    # HYG/IEF 相對強弱（負值代表高收益債跑輸無風險公債 → 信用利差擴大）
    hyg_ief_5d = round(hyg["change_pct_5d"] - ief["change_pct_5d"], 2) if (hyg and ief) else 0.0
    hyg_ief_1m = round(hyg["change_pct_1m"] - ief["change_pct_1m"], 2) if (hyg and ief) else 0.0
    lqd_ief_5d = round(lqd["change_pct_5d"] - ief["change_pct_5d"], 2) if (lqd and ief) else 0.0

    # 1) 信用利差壓力 (0~100)
    spread_stress = 32.0 + max(0.0, -hyg_ief_5d) * 14.0 + max(0.0, -hyg_ief_1m) * 6.5 + max(0.0, -lqd_ief_5d) * 8.0
    if hyg_ief_5d > 0.6:
        spread_stress -= 10.0
    spread_stress = _clamp(spread_stress)

    # 2) 利率與再融資負擔 (0~100)
    rate_stress = 35.0
    if tnx:
        if tnx.price >= 5.0:
            rate_stress = 82.0
        elif tnx.price >= 4.5:
            rate_stress = 66.0
        elif tnx.price >= 4.0:
            rate_stress = 50.0
        elif tnx.price >= 3.5:
            rate_stress = 34.0
        else:
            rate_stress = 22.0
        if tnx.change_pct_1m > 4.0:
            rate_stress += 8.0
    rate_stress = _clamp(rate_stress)

    # 3) 銀行與私募/槓桿信貸壓力 (0~100)
    bank_stress = 32.0
    if bkln:
        bank_stress += max(0.0, -bkln["change_pct_5d"]) * 14.0 + max(0.0, -bkln["change_pct_1m"]) * 7.0
    if kre:
        bank_stress += max(0.0, -kre["change_pct_5d"]) * 4.5 + max(0.0, -kre["change_pct_1m"]) * 2.5
    bank_stress = _clamp(bank_stress)

    # 4) 市場波動隱含違約壓力 (VIX)
    vix_stress = 30.0
    if vix:
        if vix.price >= 35:
            vix_stress = 88.0
        elif vix.price >= 28:
            vix_stress = 72.0
        elif vix.price >= 22:
            vix_stress = 54.0
        elif vix.price >= 16:
            vix_stress = 34.0
        else:
            vix_stress = 18.0

    derived = {
        "hyg_ief_5d": hyg_ief_5d,
        "hyg_ief_1m": hyg_ief_1m,
        "lqd_ief_5d": lqd_ief_5d,
        "spread_stress": spread_stress,
        "rate_stress": rate_stress,
        "bank_stress": bank_stress,
        "vix_stress": vix_stress,
        "tnx_price": tnx.price if tnx else None,
        "vix_price": vix.price if vix else None,
    }
    return spread_stress, derived


def _enrich_credit_news(items: List[Dict[str, Any]], max_fetch: int = 5) -> None:
    """併發預抓直接媒體網址的信用風險快訊內文，讓離線儀表板點開即有完整報導。"""
    targets = [
        it for it in items
        if it.get("link", "").startswith("http")
        and "news.google.com" not in it.get("link", "")
        and len(it.get("full_content", "")) < 450
    ][:max_fetch]
    if not targets:
        return

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(extract_article_content, it["link"], 6, 3600): it for it in targets}
        for fut, it in futs.items():
            try:
                res = fut.result()
                if res.get("ok") and res.get("full_text"):
                    it["full_content"] = res["full_text"]
                    if res.get("final_url"):
                        it["final_url"] = res["final_url"]
                    if res.get("domain"):
                        it["domain"] = res["domain"]
            except Exception:
                continue


def build_credit_radar_report(
    news_items: List[NewsItem],
    benchmarks: List[BenchmarkQuote],
    credit_proxies: List[Dict[str, Any]],
    stocks: List[StockReport],
    enrich_articles: bool = True,
) -> CreditRadarReport:
    """彙整全球債市利差、信用新聞事件與全體成分股五維信用體檢，產出 AI 信用風險雷達總報告。"""
    _, derived = compute_systemic_spread_stress(credit_proxies, benchmarks)

    # 1. 掃描全球多語系新聞中的信用風險事件
    credit_news: List[Dict[str, Any]] = []
    seen_titles = set()
    news_severity_sum = 0.0
    for n in news_items:
        hit = _detect_credit_event(n)
        if not hit:
            continue
        norm_t = n.title.strip().lower()[:60]
        if norm_t in seen_titles:
            continue
        seen_titles.add(norm_t)
        ev_name, reason, severity = hit
        news_severity_sum += severity * (1.2 if n.sentiment_score < 0 else 0.7)
        credit_news.append(
            {
                "title": n.title,
                "summary": n.summary,
                "full_content": n.full_content or n.summary,
                "source": n.source,
                "macro_region": n.macro_region,
                "lang": n.lang,
                "published_at": n.published_at,
                "event_type": ev_name,
                "reason": reason,
                "severity": severity,
                "is_official": n.is_official,
                "sentiment_label": n.sentiment_label,
                "sentiment_score": n.sentiment_score,
                "link": n.link,
            }
        )

    credit_news.sort(key=lambda x: (x["severity"], -x["sentiment_score"]), reverse=True)
    credit_news = credit_news[:14]
    if enrich_articles and credit_news:
        _enrich_credit_news(credit_news, max_fetch=5)

    news_credit_stress = _clamp(18.0 + min(75.0, news_severity_sum * 8.5))

    # 2. 統計個股信用監控名單與評等分布
    watchlist: List[Dict[str, Any]] = []
    rating_dist: Dict[str, int] = {"AAA": 0, "AA": 0, "A": 0, "BBB": 0, "BB": 0, "B": 0, "CCC": 0}
    stock_lev_list: List[float] = []
    for st in stocks:
        cr = st.credit_risk
        if not cr:
            continue
        rating_dist[cr.credit_rating] = rating_dist.get(cr.credit_rating, 0) + 1
        stock_lev_list.append(cr.dimensions.get("leverage", 35.0))
        watchlist.append(
            {
                "symbol": st.symbol,
                "name": st.name,
                "market": st.market,
                "sector_id": st.sector_id,
                "sector_name": st.sector_name,
                "risk_score": cr.risk_score,
                "credit_rating": cr.credit_rating,
                "risk_level": cr.risk_level,
                "dimensions": cr.dimensions,
                "metrics": cr.metrics,
                "top_flag": cr.red_flags[0] if cr.red_flags else "",
                "red_flags": cr.red_flags,
                "buffers": cr.buffers,
                "ai_diagnosis": cr.ai_diagnosis,
            }
        )
    watchlist.sort(key=lambda x: x["risk_score"], reverse=True)

    avg_corp_lev = (sum(stock_lev_list) / len(stock_lev_list)) if stock_lev_list else 36.0

    # 五維系統性信用雷達（對齊個股 5 軸，便於同一張雷達圖雙層疊加比較）
    sys_dims = {
        "leverage": _clamp(derived["spread_stress"] * 0.65 + avg_corp_lev * 0.35),
        "liquidity": derived["rate_stress"],
        "cashflow": derived["bank_stress"],
        "market_stress": derived["vix_stress"],
        "event_risk": news_credit_stress,
    }

    systemic_score = _clamp(
        sys_dims["leverage"] * 0.26
        + sys_dims["liquidity"] * 0.20
        + sys_dims["cashflow"] * 0.18
        + sys_dims["market_stress"] * 0.20
        + sys_dims["event_risk"] * 0.16
    )
    risk_level = _risk_level_from_score(systemic_score)

    hyg_ief_5d = derived["hyg_ief_5d"]
    if derived["spread_stress"] >= 68 or hyg_ief_5d <= -1.8:
        spread_regime = "系統性信用壓力"
    elif derived["spread_stress"] >= 50 or hyg_ief_5d <= -0.9:
        spread_regime = "信用利差緊繃"
    elif derived["spread_stress"] >= 36 or hyg_ief_5d <= -0.3:
        spread_regime = "利差溫和擴大"
    else:
        spread_regime = "信用利差穩定"

    # 3. 組合展示用信用代理指標卡
    proxies_display: List[Dict[str, Any]] = [
        {
            "symbol": "HYG/IEF",
            "name": "高收益債相對公債利差動能",
            "category": "核心利差指標",
            "price": None,
            "change_pct_1d": 0.0,
            "change_pct_5d": hyg_ief_5d,
            "change_pct_1m": derived["hyg_ief_1m"],
            "status": "利差擴大警戒" if hyg_ief_5d <= -0.8 else ("利差微擴" if hyg_ief_5d < -0.2 else "利差受控"),
            "is_stress": hyg_ief_5d <= -0.5,
        }
    ]
    for p in credit_proxies:
        c5 = p.get("change_pct_5d", 0.0)
        is_ief = p["symbol"] == "IEF"
        proxies_display.append(
            {
                "symbol": p["symbol"],
                "name": p["name"],
                "category": p["category"],
                "price": p.get("price"),
                "change_pct_1d": p.get("change_pct_1d", 0.0),
                "change_pct_5d": c5,
                "change_pct_1m": p.get("change_pct_1m", 0.0),
                "status": "避險買盤" if (is_ief and c5 > 0.3) else ("信用承壓" if (not is_ief and c5 <= -1.0) else "平穩"),
                "is_stress": (not is_ief and c5 <= -1.0),
            }
        )

    # 4. 生成 AI 信用風險總評與具體警告
    key_warnings: List[str] = []
    mitigations: List[str] = []

    if hyg_ief_5d <= -0.5:
        key_warnings.append(
            f"美國高收益債 (HYG) 近 5 日跑輸公債 (IEF) {hyg_ief_5d:+.2f}%（近月 {derived['hyg_ief_1m']:+.2f}%），顯示垃圾債信用利差正實質擴大。"
        )
    else:
        mitigations.append(f"高收益債相對公債近 5 日變動 {hyg_ief_5d:+.2f}%，債市尚未出現全面流動性擠兌。")

    if derived["tnx_price"] and derived["tnx_price"] >= 4.5:
        key_warnings.append(
            f"美國 10 年期公債殖利率高達 {derived['tnx_price']:.2f}%，高槓桿企業與 AI 資本支出舉債之再融資利息壓力沉重。"
        )
    if derived["vix_price"] and derived["vix_price"] >= 25:
        key_warnings.append(
            f"恐慌指數 VIX 位於 {derived['vix_price']:.2f} 高檔，權益波動擴大壓縮企業 Merton 違約緩衝距離。"
        )

    high_risk_stocks = [w for w in watchlist if w["risk_score"] >= 48]
    if high_risk_stocks:
        names = "、".join(f"{w['name']}({w['symbol']} {w['credit_rating']})" for w in high_risk_stocks[:3])
        key_warnings.append(f"追蹤標的中有 {len(high_risk_stocks)} 檔信用風險指數達警戒以上：{names}。")

    if credit_news:
        top_cn = credit_news[0]
        key_warnings.append(f"全球信用情報偵測 {len(credit_news)} 則事件，重點警戒【{top_cn['event_type']}】：「{top_cn['title'][:52]}」。")

    ig_count = sum(rating_dist.get(g, 0) for g in ("AAA", "AA", "A", "BBB"))
    if watchlist:
        mitigations.append(
            f"本系統追蹤之 {len(watchlist)} 檔美台龍頭股中，共有 {ig_count} 檔維持投資級以上 AI 模擬信評（BBB 以上），整體大型股現金流護城河相對穩健。"
        )
    if not key_warnings:
        key_warnings.append("目前跨市場債市利差與追蹤企業財務結構整體可控，無立即系統性違約警報。")
    mitigations.append("建議避開「高負債比＋自由現金流為負＋股價深幅回撤」三重疊加之標的，優先配置淨現金與高 FCF 企業。")

    ai_summary = (
        f"AI 信用風險雷達綜合全球高收益債利差（HYG/IEF 近5日 {hyg_ief_5d:+.2f}%）、"
        f"美債殖利率（{derived['tnx_price']:.2f}% 基準）" if derived["tnx_price"] else
        f"AI 信用風險雷達綜合全球高收益債利差（HYG/IEF 近5日 {hyg_ief_5d:+.2f}%）"
    )
    ai_summary += (
        f"、槓桿貸款／銀行板塊與 {len(credit_news)} 則全球信用風險情報，判定當前系統性信用環境為「{risk_level}」（總指數 {systemic_score:.1f} / 100，{spread_regime}）。"
        f"在 {len(watchlist)} 檔美台標的體檢中，共有 {len(high_risk_stocks)} 檔亮起中度以上信用警戒燈號。"
    )

    return CreditRadarReport(
        systemic_score=systemic_score,
        risk_level=risk_level,
        spread_regime=spread_regime,
        dimensions=sys_dims,
        dimension_labels=RADAR_DIMENSIONS,
        proxies=proxies_display,
        ai_summary=ai_summary,
        key_warnings=key_warnings[:5],
        mitigations=mitigations[:3],
        credit_news=credit_news,
        watchlist=watchlist,
        rating_distribution=rating_dist,
    )
