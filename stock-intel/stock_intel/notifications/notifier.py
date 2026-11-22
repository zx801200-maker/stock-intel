"""多管道投資決策簡報推播引擎（LINE Messaging API Flex 卡片 / Telegram / Discord / Email SMTP）。"""

from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List

from stock_intel.config import OUTPUT_DIR

SESSION_LABELS = {
    "tw_premarket": "台股盤前投資決策簡報（08:15 台北時間）",
    "us_premarket": "美股盤前投資決策簡報（20:45 台北時間）",
    "daily": "全球股市即時情報與多空推演簡報",
}


def _select_focus_stocks(report: Dict[str, Any], session: str) -> List[Dict[str, Any]]:
    stocks = report.get("stocks") or []
    wl_syms = {str(w.get("symbol", "")).upper() for w in (report.get("watchlist") or [])}
    wl_stocks = [s for s in stocks if s["symbol"].upper() in wl_syms]
    rest = [s for s in stocks if s["symbol"].upper() not in wl_syms]

    if session == "tw_premarket":
        ordered = (
            [s for s in wl_stocks if s["market"] == "TW"]
            + [s for s in wl_stocks if s["market"] == "US"]
            + [s for s in rest if s["market"] == "TW"][:4]
            + [s for s in rest if s["market"] == "US"][:2]
        )
        return ordered[:6]
    if session == "us_premarket":
        ordered = (
            [s for s in wl_stocks if s["market"] == "US"]
            + [s for s in wl_stocks if s["market"] == "TW"]
            + [s for s in rest if s["market"] == "US"][:4]
            + [s for s in rest if s["market"] == "TW"][:2]
        )
        return ordered[:6]
    return (wl_stocks + rest)[:5]


def format_push_brief(report: Dict[str, Any], session: str = "daily") -> str:
    """根據盤前場次（台股盤前／美股盤前）濃縮產出精煉的即時決策推播純文字訊息。"""
    macro = report["macro"]
    sectors = report.get("sectors") or []
    news = report.get("news") or []
    title = SESSION_LABELS.get(session, SESSION_LABELS["daily"])

    lines: List[str] = [
        f"【{title}】",
        f"時間 (UTC): {report['generated_at'][:16].replace('T', ' ')} | 全球情資: {report['news_count']} 則",
        "",
        f"■ 大盤走向判定：{macro['stance']}（多空指數 {macro['overall_score']:+.1f} / 信心度 {macro['confidence']}%）",
        f"  新聞情緒 {macro['news_sentiment_score']:+.1f} | 市場動能 {macro['market_momentum_score']:+.1f} | 風險環境 {macro['risk_index_score']:+.1f}",
    ]

    reg_sum = macro.get("region_summary") or []
    if reg_sum:
        reg_bits = " / ".join(f"{r['region']}({r['avg_score']:+.0f})" for r in reg_sum[:5])
        lines.append(f"  全球區域情緒：{reg_bits}")

    bm_map = {b["symbol"]: b for b in (macro.get("benchmarks") or [])}
    bm_parts = []
    for sym, short in (("^GSPC", "S&P500"), ("^SOX", "費半"), ("^TWII", "台股"), ("^VIX", "VIX")):
        if sym in bm_map:
            b = bm_map[sym]
            bm_parts.append(f"{short} {b['price']:.1f}({b['change_pct_1d']:+.1f}%)")
    if bm_parts:
        lines.append("  核心指數：" + " | ".join(bm_parts))

    tw_inst = macro.get("tw_institutional")
    if tw_inst and tw_inst.get("date"):
        lines.append(
            f"■ 台股三大法人({tw_inst['date']})：合計 {tw_inst['total_net_billion']:+.2f} 億 "
            f"（外資 {tw_inst['foreign_net_billion']:+.2f} 億 / 投信 {tw_inst['trust_net_billion']:+.2f} 億 / 自營 {tw_inst['dealer_net_billion']:+.2f} 億）"
        )

    bull_secs = report.get("bullish_sectors") or sectors[:3]
    bear_secs = report.get("bearish_sectors") or list(reversed(sectors))[:3]

    lines.append("")
    lines.append("■ 產業利多／抗跌推薦 Top 3（含消息面要素）：")
    for idx, s in enumerate(bull_secs[:3], 1):
        reason = s.get("news_summary_reason") or (s["key_drivers"][0] if s.get("key_drivers") else "")
        lines.append(f"  {idx}. {s['name']} — {s['score']:.1f}分 ({s['outlook_label']})")
        if reason:
            lines.append(f"     ▸ {reason[:78]}")

    lines.append("")
    lines.append("■ 產業利空／警戒避開 Top 3（含消息面事由）：")
    for idx, s in enumerate(bear_secs[:3], 1):
        bear_news = s.get("bearish_catalysts_news") or []
        if bear_news:
            b0 = bear_news[0]
            reason = f"【{b0['event_type']}】{b0['reason']}（{b0['source']}：{str(b0['title'])[:36]}）"
        else:
            reason = s.get("news_summary_reason") or (s["key_risks"][0] if s.get("key_risks") else "")
        lines.append(f"  {idx}. {s['name']} — {s['score']:.1f}分 ({s['outlook_label']})")
        if reason:
            lines.append(f"     ▸ {reason[:78]}")

    focus_stocks = _select_focus_stocks(report, session)
    lines.append("")
    lines.append("■ 盤前重點關注標的（基本面 / 技術面 / 策略回測）：")
    for st in focus_stocks:
        f = st["fundamental"]
        t = st["technical"]
        bt = st.get("backtest")
        bt_str = (
            f" | 回測 {bt['best_total_return_pct']:+.1f}%(勝率{bt['best_win_rate_pct']:.0f}%・{bt['best_current_signal']})"
            if bt
            else ""
        )
        inst = st.get("institutional")
        inst_str = f" | 法人{inst['total_net_lots']:+,d}張" if inst and inst.get("total_net_lots") is not None else ""
        lines.append(
            f"  • {st['name']}({st['symbol']}) [{st['rating']} {st['total_score']:.0f}分] "
            f"價{t['price']:.1f}({t['change_pct_1d']:+.1f}%) | 基本{f['grade']} / 技術{t['trend_label']}{inst_str}{bt_str}"
        )

    lines.append("")
    lines.append("■ 全球高訊號焦點情報：")
    for n in news[:4]:
        ev = f"【{n['event_type']}】" if n.get("event_type") else ""
        lines.append(f"  [{n.get('macro_region', n['region'])}|{n['sentiment_label']}]{ev} {n['title'][:60]}")

    if macro.get("action_plan"):
        lines.append("")
        lines.append("■ 盤前操作紀律：")
        for a in macro["action_plan"][:2]:
            lines.append(f"  ▸ {a}")

    return "\n".join(lines)


def _make_dashboard_footer(page_hint: str, dashboard_url: str = "") -> Dict[str, Any]:
    contents: List[Dict[str, Any]] = []
    if dashboard_url and dashboard_url.startswith("https://"):
        contents.append(
            {
                "type": "button",
                "style": "primary",
                "color": "#1B4F8A",
                "height": "sm",
                "action": {
                    "type": "uri",
                    "label": "打開完整互動儀表板",
                    "uri": dashboard_url[:950],
                },
            }
        )
    contents.append(
        {
            "type": "text",
            "text": page_hint,
            "size": "xxs",
            "color": "#888888",
            "align": "center",
            "margin": "sm" if contents else "none",
        }
    )
    return {
        "type": "box",
        "layout": "vertical",
        "paddingAll": "10px",
        "backgroundColor": "#F8F7F3",
        "contents": contents,
    }


def build_line_flex_message(
    report: Dict[str, Any],
    session: str = "daily",
    dashboard_url: str | None = None,
) -> Dict[str, Any]:
    """建構 LINE Messaging API 3 張可左右滑動 Flex Carousel 卡片（大盤產業 / 自選股與回測 / AI信用雷達），並支援底部直開完整互動儀表板按鈕。"""
    macro = report["macro"]
    sectors = report.get("sectors") or []
    bull_secs = report.get("bullish_sectors") or sectors[:3]
    bear_secs = report.get("bearish_sectors") or list(reversed(sectors))[:3]
    news = report.get("news") or []
    focus_stocks = _select_focus_stocks(report, session)
    wl_syms = {str(w.get("symbol", "")).upper() for w in (report.get("watchlist") or [])}
    title = SESSION_LABELS.get(session, SESSION_LABELS["daily"])
    dash_url = (dashboard_url if dashboard_url is not None else os.getenv("DASHBOARD_URL", "")).strip()

    score = float(macro.get("overall_score", 0.0))
    if score >= 10:
        header_bg = "#0D7A52"
    elif score <= -10:
        header_bg = "#B83232"
    else:
        header_bg = "#9A6412"

    def _val_color(v: float, invert: bool = False) -> str:
        eff = -v if invert else v
        return "#0D7A52" if eff > 0.05 else ("#C23636" if eff < -0.05 else "#666666")

    def _safe_txt(val: Any, fallback: str = "—") -> str:
        s = str(val or "").strip()
        return s if s else fallback

    # =========================================================================
    # 卡片 1/3：大盤多空推演 × 三大法人 × 利多／利空產業排行（含消息面事由）
    # =========================================================================
    c1_body: List[Dict[str, Any]] = []

    reg_sum = macro.get("region_summary") or []
    if reg_sum:
        reg_text = " ｜ ".join(f"{r['region']} {r['avg_score']:+.0f}" for r in reg_sum[:6])
        c1_body.append(
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#F5F4EF",
                "cornerRadius": "8px",
                "paddingAll": "10px",
                "contents": [
                    {"type": "text", "text": "全球區域新聞情緒", "size": "xs", "weight": "bold", "color": "#555555"},
                    {"type": "text", "text": _safe_txt(reg_text), "size": "xs", "color": "#222222", "wrap": True, "margin": "xs"},
                ],
            }
        )

    bm_map = {b["symbol"]: b for b in (macro.get("benchmarks") or [])}
    bm_rows: List[Dict[str, Any]] = []
    for sym, label in (("^GSPC", "標普500"), ("^SOX", "費城半導體"), ("^TWII", "台股加權"), ("^VIX", "恐慌VIX")):
        if sym in bm_map:
            b = bm_map[sym]
            bm_rows.append(
                {
                    "type": "box",
                    "layout": "baseline",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": label, "size": "xs", "color": "#555555", "flex": 4},
                        {"type": "text", "text": f"{b['price']:.1f}", "size": "xs", "weight": "bold", "align": "end", "flex": 3},
                        {
                            "type": "text",
                            "text": f"{b['change_pct_1d']:+.1f}% (5D {b['change_pct_5d']:+.1f}%)",
                            "size": "xxs",
                            "color": _val_color(b["change_pct_1d"], b.get("invert_sentiment", False)),
                            "align": "end",
                            "flex": 5,
                        },
                    ],
                }
            )
    if bm_rows:
        c1_body.extend(
            [
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": "跨市場核心指數", "size": "xs", "weight": "bold", "color": "#1B4F8A", "margin": "md"},
                *bm_rows,
            ]
        )

    tw_inst = macro.get("tw_institutional")
    if tw_inst and tw_inst.get("date"):
        c1_body.extend(
            [
                {"type": "separator", "margin": "md"},
                {
                    "type": "box",
                    "layout": "baseline",
                    "margin": "md",
                    "contents": [
                        {"type": "text", "text": f"台股三大法人 ({tw_inst['date']})", "size": "xs", "weight": "bold", "color": "#1B4F8A", "flex": 6},
                        {
                            "type": "text",
                            "text": f"合計 {tw_inst['total_net_billion']:+.1f}億",
                            "size": "xs",
                            "weight": "bold",
                            "color": _val_color(tw_inst["total_net_billion"]),
                            "align": "end",
                            "flex": 4,
                        },
                    ],
                },
                {
                    "type": "text",
                    "text": f"外資 {tw_inst['foreign_net_billion']:+.1f}億 ｜ 投信 {tw_inst['trust_net_billion']:+.1f}億 ｜ 自營 {tw_inst['dealer_net_billion']:+.1f}億",
                    "size": "xxs",
                    "color": "#444444",
                    "wrap": True,
                    "margin": "xs",
                },
            ]
        )

    if bull_secs:
        c1_body.append({"type": "separator", "margin": "md"})
        c1_body.append({"type": "text", "text": "▲ 產業利多／抗跌推薦（點擊驗證來源）", "size": "xs", "weight": "bold", "color": "#0D7A52", "margin": "md"})
        for idx, s in enumerate(bull_secs[:3], 1):
            bull_n = s.get("bullish_catalysts_news") or []
            ev_link = ""
            if bull_n:
                ev_txt = f"【{bull_n[0]['event_type']}】{str(bull_n[0]['title'])[:44]}"
                ev_link = str(bull_n[0].get("link") or "")
            else:
                ev_txt = str(s.get("news_summary_reason") or (s.get("key_drivers") or ["基本面支撐"])[0])[:52]
            box: Dict[str, Any] = {
                "type": "box",
                "layout": "vertical",
                "margin": "xs",
                "contents": [
                    {
                        "type": "box",
                        "layout": "baseline",
                        "contents": [
                            {"type": "text", "text": f"{idx}. {s['name']}", "size": "xs", "weight": "bold", "color": "#111111", "flex": 6},
                            {"type": "text", "text": f"{s['score']:.1f}分 ({s['outlook_label']})", "size": "xs", "weight": "bold", "color": "#0D7A52", "align": "end", "flex": 4},
                        ],
                    },
                    {"type": "text", "text": _safe_txt(ev_txt) + (" ↗" if ev_link.startswith("https://") else ""), "size": "xxs", "color": "#555555", "wrap": True},
                ],
            }
            if ev_link.startswith("https://") and len(ev_link) <= 950:
                box["action"] = {"type": "uri", "label": "查看來源", "uri": ev_link}
            c1_body.append(box)

    if bear_secs:
        c1_body.append({"type": "separator", "margin": "md"})
        c1_body.append({"type": "text", "text": "▼ 產業利空／警戒避開（點擊驗證來源）", "size": "xs", "weight": "bold", "color": "#C23636", "margin": "md"})
        for idx, s in enumerate(bear_secs[:3], 1):
            bear_n = s.get("bearish_catalysts_news") or []
            ev_link = ""
            if bear_n:
                ev_txt = f"【{bear_n[0]['event_type']}】{str(bear_n[0]['title'])[:44]}"
                ev_link = str(bear_n[0].get("link") or "")
            else:
                ev_txt = str(s.get("news_summary_reason") or (s.get("key_risks") or ["承壓偏弱"])[0])[:52]
            box = {
                "type": "box",
                "layout": "vertical",
                "margin": "xs",
                "contents": [
                    {
                        "type": "box",
                        "layout": "baseline",
                        "contents": [
                            {"type": "text", "text": f"{idx}. {s['name']}", "size": "xs", "weight": "bold", "color": "#111111", "flex": 6},
                            {"type": "text", "text": f"{s['score']:.1f}分 ({s['outlook_label']})", "size": "xs", "weight": "bold", "color": "#C23636", "align": "end", "flex": 4},
                        ],
                    },
                    {"type": "text", "text": _safe_txt(ev_txt) + (" ↗" if ev_link.startswith("https://") else ""), "size": "xxs", "color": "#663333", "wrap": True},
                ],
            }
            if ev_link.startswith("https://") and len(ev_link) <= 950:
                box["action"] = {"type": "uri", "label": "查看來源", "uri": ev_link}
            c1_body.append(box)

    if not c1_body:
        c1_body.append({"type": "text", "text": "暫無大盤詳細資料", "size": "xs", "color": "#666666"})

    bubble_macro = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": header_bg,
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": f"{title} (1/3)", "color": "#FFFFFFCC", "size": "xs", "weight": "bold"},
                {
                    "type": "box",
                    "layout": "baseline",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": f"{macro['stance']}  {score:+.1f}", "color": "#FFFFFF", "size": "xl", "weight": "bold", "flex": 7},
                        {"type": "text", "text": f"信心 {macro['confidence']}%", "color": "#FFFFFFEE", "size": "xs", "align": "end", "flex": 3},
                    ],
                },
                {
                    "type": "text",
                    "text": f"全球 {report['news_count']} 則多語情資 ｜ UTC {report['generated_at'][:16].replace('T', ' ')}",
                    "color": "#FFFFFFBB",
                    "size": "xxs",
                    "margin": "xs",
                },
            ],
        },
        "body": {"type": "box", "layout": "vertical", "paddingAll": "14px", "contents": c1_body},
        "footer": _make_dashboard_footer("1/3 ・ 往左滑看「自選股與個股回測」→", dash_url),
    }

    # =========================================================================
    # 卡片 2/3：★自選股 × 盤前重點個股（基本／技術／法人／2年回測／直擊新聞）
    # =========================================================================
    c2_body: List[Dict[str, Any]] = []
    if focus_stocks:
        c2_body.append({"type": "text", "text": "★ 自選股優先 × 盤前重點關注標的", "size": "xs", "weight": "bold", "color": "#1B4F8A"})
        for st in focus_stocks[:5]:
            f = st["fundamental"]
            t = st["technical"]
            inst = st.get("institutional")
            bt = st.get("backtest")
            is_wl = str(st.get("symbol", "")).upper() in wl_syms
            prefix = "★ " if is_wl else ""
            sub_parts = [f"基本{f['grade']}", f"技術{t['trend_label']}"]
            if inst and inst.get("total_net_lots") is not None:
                sub_parts.append(f"法人{inst['total_net_lots']:+,d}張")
            if bt:
                sub_parts.append(f"回測{bt['best_total_return_pct']:+.0f}%({bt['best_current_signal']})")
            st_contents: List[Dict[str, Any]] = [
                {
                    "type": "box",
                    "layout": "baseline",
                    "contents": [
                        {"type": "text", "text": f"{prefix}{st['name']} ({st['symbol']})", "size": "xs", "weight": "bold", "color": "#111111", "flex": 6},
                        {
                            "type": "text",
                            "text": f"{t['price']:.1f} ({t['change_pct_1d']:+.1f}%)",
                            "size": "xs",
                            "weight": "bold",
                            "color": _val_color(t["change_pct_1d"]),
                            "align": "end",
                            "flex": 4,
                        },
                    ],
                },
                {"type": "text", "text": " ・ ".join(sub_parts), "size": "xxs", "color": "#555555", "wrap": True},
            ]
            # 嚴格只顯示真正直接相關的個股即時新聞（無新聞絕不硬塞）
            rel_news = st.get("related_news") or []
            if rel_news:
                n0 = rel_news[0]
                n0_link = str(n0.get("link") or "")
                n0_box: Dict[str, Any] = {
                    "type": "text",
                    "text": f"📰 [{n0.get('sentiment_label', '中性')}] {str(n0.get('title', ''))[:48]}" + (" ↗" if n0_link.startswith("https://") else ""),
                    "size": "xxs",
                    "color": "#1B4F8A" if n0_link.startswith("https://") else "#444444",
                    "wrap": True,
                    "margin": "xs",
                }
                if n0_link.startswith("https://") and len(n0_link) <= 950:
                    n0_box["action"] = {"type": "uri", "label": "閱讀個股新聞", "uri": n0_link}
                st_contents.append(n0_box)
            c2_body.append(
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "sm",
                    "paddingAll": "8px",
                    "backgroundColor": "#FFFBEF" if is_wl else "#F8F9FA",
                    "cornerRadius": "8px",
                    "contents": st_contents,
                }
            )

    if news:
        c2_body.append({"type": "separator", "margin": "md"})
        c2_body.append({"type": "text", "text": "全球高訊號焦點頭條（點擊看原文）", "size": "xs", "weight": "bold", "color": "#1B4F8A", "margin": "md"})
        for n in news[:3]:
            reg = n.get("macro_region", n.get("region", "全球"))
            lnk = str(n.get("link") or "")
            ntxt: Dict[str, Any] = {
                "type": "text",
                "text": f"• [{reg}|{n['sentiment_label']}] {str(n['title'])[:58]}" + (" ↗" if lnk.startswith("https://") else ""),
                "size": "xxs",
                "color": "#333333",
                "wrap": True,
                "margin": "xs",
            }
            if lnk.startswith("https://") and len(lnk) <= 950:
                ntxt["action"] = {"type": "uri", "label": "開啟原文", "uri": lnk}
            c2_body.append(ntxt)

    if not c2_body:
        c2_body.append({"type": "text", "text": "尚無個股追蹤資料", "size": "xs", "color": "#666666"})

    bubble_stocks = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1B4F8A",
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "自選股 × 重點個股 × 焦點新聞 (2/3)", "color": "#FFFFFFCC", "size": "xs", "weight": "bold"},
                {"type": "text", "text": f"追蹤 {len(wl_syms)} 檔自選股 ｜ 共 {len(focus_stocks)} 檔精選", "color": "#FFFFFF", "size": "lg", "weight": "bold", "margin": "xs"},
                {"type": "text", "text": "基本面評級 ・ 技術面趨勢 ・ 2年策略回測 ・ 嚴格過濾直擊新聞", "color": "#FFFFFFBB", "size": "xxs", "margin": "xs"},
            ],
        },
        "body": {"type": "box", "layout": "vertical", "paddingAll": "14px", "contents": c2_body},
        "footer": _make_dashboard_footer("2/3 ・ 往左滑看「AI 信用風險雷達」→", dash_url),
    }

    # =========================================================================
    # 卡片 3/3：AI 信用風險雷達 × 高危企業警戒 × 盤前操作紀律
    # =========================================================================
    cr = report.get("credit_radar") or {}
    cr_score = float(cr.get("systemic_score", 0.0))
    cr_bg = "#B83232" if cr_score >= 48 else ("#9A6412" if cr_score >= 30 else "#0D7A52")
    c3_body: List[Dict[str, Any]] = []

    if cr:
        c3_body.append(
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#F5F4EF",
                "cornerRadius": "8px",
                "paddingAll": "10px",
                "contents": [
                    {"type": "text", "text": f"利差狀態：{_safe_txt(cr.get('spread_regime'))}", "size": "xs", "weight": "bold", "color": "#222222"},
                    {"type": "text", "text": _safe_txt(cr.get("ai_summary"), "信用市場監測中")[:150], "size": "xxs", "color": "#444444", "wrap": True, "margin": "xs"},
                ],
            }
        )

        proxies = cr.get("credit_proxies") or []
        if proxies:
            c3_body.append({"type": "separator", "margin": "md"})
            c3_body.append({"type": "text", "text": "全球信用債／銀行指標", "size": "xs", "weight": "bold", "color": "#1B4F8A", "margin": "md"})
            for p in proxies[:4]:
                c3_body.append(
                    {
                        "type": "box",
                        "layout": "baseline",
                        "margin": "xs",
                        "contents": [
                            {"type": "text", "text": f"{p['symbol']} ({p.get('category', '')})", "size": "xs", "color": "#444444", "flex": 5},
                            {"type": "text", "text": f"{float(p.get('price', 0)):.1f}", "size": "xs", "weight": "bold", "align": "end", "flex": 2},
                            {
                                "type": "text",
                                "text": f"1D {float(p.get('change_pct_1d', 0)):+.1f}% / 5D {float(p.get('change_pct_5d', 0)):+.1f}%",
                                "size": "xxs",
                                "color": _val_color(float(p.get("change_pct_5d", 0))),
                                "align": "end",
                                "flex": 5,
                            },
                        ],
                    }
                )

        wlist = cr.get("watchlist") or []
        if wlist:
            c3_body.append({"type": "separator", "margin": "md"})
            c3_body.append({"type": "text", "text": "高信用風險警戒個股 Top 4", "size": "xs", "weight": "bold", "color": "#C23636", "margin": "md"})
            for w in wlist[:4]:
                r_sc = float(w.get("risk_score", 0.0))
                r_col = "#C23636" if r_sc >= 48 else ("#B87414" if r_sc >= 30 else "#0D7A52")
                c3_body.append(
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "xs",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {"type": "text", "text": f"{w['name']} ({w['symbol']})", "size": "xs", "weight": "bold", "color": "#111111", "flex": 6},
                                    {"type": "text", "text": f"信評 {w['credit_rating']}・{r_sc:.0f}分", "size": "xs", "weight": "bold", "color": r_col, "align": "end", "flex": 4},
                                ],
                            },
                            {"type": "text", "text": _safe_txt(w.get("top_flag"), w.get("risk_level", ""))[:60], "size": "xxs", "color": "#666666", "wrap": True},
                        ],
                    }
                )

        cnews = cr.get("credit_news") or []
        if cnews:
            c3_body.append({"type": "separator", "margin": "md"})
            c3_body.append({"type": "text", "text": "企業信用／債市違約快訊", "size": "xs", "weight": "bold", "color": "#1B4F8A", "margin": "md"})
            for cn in cnews[:2]:
                clnk = str(cn.get("link") or "")
                cn_txt: Dict[str, Any] = {
                    "type": "text",
                    "text": f"• {str(cn.get('title', ''))[:58]}" + (" ↗" if clnk.startswith("https://") else ""),
                    "size": "xxs",
                    "color": "#444444",
                    "wrap": True,
                    "margin": "xs",
                }
                if clnk.startswith("https://") and len(clnk) <= 950:
                    cn_txt["action"] = {"type": "uri", "label": "閱讀信用快訊", "uri": clnk}
                c3_body.append(cn_txt)

    if macro.get("action_plan"):
        c3_body.append({"type": "separator", "margin": "md"})
        c3_body.append({"type": "text", "text": "盤前操作紀律提醒", "size": "xs", "weight": "bold", "color": "#1B4F8A", "margin": "md"})
        for act in macro["action_plan"][:2]:
            c3_body.append({"type": "text", "text": f"• {_safe_txt(act)[:78]}", "size": "xxs", "color": "#333333", "wrap": True, "margin": "xs"})

    if not c3_body:
        c3_body.append({"type": "text", "text": "本次尚無信用雷達異常警示。", "size": "xs", "color": "#666666"})

    bubble_credit = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": cr_bg,
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "AI 信用風險雷達 (3/3)", "color": "#FFFFFFCC", "size": "xs", "weight": "bold"},
                {
                    "type": "box",
                    "layout": "baseline",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": f"{_safe_txt(cr.get('risk_level'), '系統監測中')}", "color": "#FFFFFF", "size": "lg", "weight": "bold", "flex": 7},
                        {"type": "text", "text": f"{cr_score:.1f}/100", "color": "#FFFFFFEE", "size": "md", "weight": "bold", "align": "end", "flex": 3},
                    ],
                },
                {"type": "text", "text": "高收益債利差 ・ 區域銀行壓力 ・ 個股模擬信評 AAA–CCC", "color": "#FFFFFFBB", "size": "xxs", "margin": "xs"},
            ],
        },
        "body": {"type": "box", "layout": "vertical", "paddingAll": "14px", "contents": c3_body},
        "footer": _make_dashboard_footer("3/3 ・ Stock Intel 量化研究簡報・僅供參考", dash_url),
    }

    alt_text = f"{title}｜{macro['stance']}({score:+.1f})｜信用雷達{cr_score:.0f}分｜往左滑看3張完整卡片"[:390]

    return {
        "type": "flex",
        "altText": alt_text,
        "contents": {
            "type": "carousel",
            "contents": [bubble_macro, bubble_stocks, bubble_credit],
        },
    }


def _line_http_post(url: str, token: str, payload: Dict[str, Any]) -> int:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return int(r.status)


def _send_line(text: str, report: Dict[str, Any], session: str) -> Dict[str, Any]:
    """
    支援新版 LINE Messaging API：
    - 預設發送精美 Flex 互動卡片（LINE_FORMAT=flex），若失敗自動降級純文字。
    - 支援單一或逗號分隔多個 LINE_USER_ID（個人 Uxxx 或群組 Cxxx）。
    - 若未填 LINE_USER_ID，自動改用 Broadcast 廣播給所有加入該官方帳號的好友（免查 User ID！）。
    """
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    raw_targets = os.getenv("LINE_USER_ID", "").strip()
    fmt_mode = os.getenv("LINE_FORMAT", "flex").strip().lower()

    if not token:
        return {"channel": "line", "status": "skipped", "reason": "未設定 LINE_CHANNEL_ACCESS_TOKEN"}

    flex_msg = build_line_flex_message(report, session=session)
    text_msg = {"type": "text", "text": text[:4800]}
    primary_msg = text_msg if fmt_mode == "text" else flex_msg

    targets = [t.strip() for t in raw_targets.split(",") if t.strip()]
    mode = "push" if targets else "broadcast"

    try:
        if mode == "broadcast":
            status = _line_http_post(
                "https://api.line.me/v2/bot/message/broadcast",
                token,
                {"messages": [primary_msg]},
            )
            return {"channel": "line", "status": "sent", "mode": "broadcast", "format": primary_msg["type"], "http_status": status}

        sent_count = 0
        for target_id in targets:
            _line_http_post(
                "https://api.line.me/v2/bot/message/push",
                token,
                {"to": target_id, "messages": [primary_msg]},
            )
            sent_count += 1
        return {"channel": "line", "status": "sent", "mode": "push", "targets": sent_count, "format": primary_msg["type"]}
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")[:260]
        # 若 Flex 卡片因特殊字元遭拒 (HTTP 400)，自動降級改送純文字確保送達
        if primary_msg["type"] == "flex" and err.code == 400:
            if mode == "broadcast":
                status = _line_http_post("https://api.line.me/v2/bot/message/broadcast", token, {"messages": [text_msg]})
                return {"channel": "line", "status": "sent", "mode": "broadcast", "format": "text_fallback", "http_status": status}
            for target_id in targets:
                _line_http_post("https://api.line.me/v2/bot/message/push", token, {"to": target_id, "messages": [text_msg]})
            return {"channel": "line", "status": "sent", "mode": "push", "targets": len(targets), "format": "text_fallback"}
        return {"channel": "line", "status": "failed", "http_status": err.code, "reason": err_body}


def verify_line_bot(send_test: bool = False, report: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """驗證 LINE_CHANNEL_ACCESS_TOKEN 有效性，並可選擇發送一則測試訊息。"""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        return {"ok": False, "error": "尚未在 .env 設定 LINE_CHANNEL_ACCESS_TOKEN。請參閱 docs/LINE_SETUP.md。"}

    req = urllib.request.Request(
        "https://api.line.me/v2/bot/info",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            bot_info = json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as err:
        return {"ok": False, "http_status": err.code, "error": err.read().decode("utf-8", errors="replace")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    out: Dict[str, Any] = {
        "ok": True,
        "bot_name": bot_info.get("displayName"),
        "basic_id": bot_info.get("basicId"),
        "mode": "push" if os.getenv("LINE_USER_ID", "").strip() else "broadcast (自動廣播給所有好友)",
    }
    if send_test and report:
        brief = format_push_brief(report, session="tw_premarket")
        out["push_result"] = _send_line(brief, report, session="tw_premarket")
    return out


def _send_telegram(text: str) -> Dict[str, Any]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"channel": "telegram", "status": "skipped", "reason": "未設定 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return {"channel": "telegram", "status": "sent", "http_status": r.status}


def _send_discord(text: str, report: Dict[str, Any], session: str) -> Dict[str, Any]:
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        return {"channel": "discord", "status": "skipped", "reason": "未設定 DISCORD_WEBHOOK_URL"}

    score = float((report.get("macro") or {}).get("overall_score", 0.0))
    color = 0x0D8A5A if score >= 10 else (0xC93B3B if score <= -10 else 0xD98A1A)
    payload = {
        "username": "Stock Intel 智策股市情報",
        "embeds": [
            {
                "title": SESSION_LABELS.get(session, SESSION_LABELS["daily"]),
                "description": text[:3900],
                "color": color,
                "footer": {"text": "Stock Intel 跨市場多空推演系統・僅供研究參考"},
            }
        ],
    }
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "StockIntelBot/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return {"channel": "discord", "status": "sent", "http_status": r.status}


def _send_email(text: str, session: str) -> Dict[str, Any]:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip()
    to_addr = os.getenv("EMAIL_TO", "").strip()
    if not (host and user and password and to_addr):
        return {"channel": "email", "status": "skipped", "reason": "未完整設定 SMTP_HOST / SMTP_USER / SMTP_PASS / EMAIL_TO"}

    port = int(os.getenv("SMTP_PORT", "587") or "587")
    msg = EmailMessage()
    msg["Subject"] = SESSION_LABELS.get(session, SESSION_LABELS["daily"])
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(text)

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return {"channel": "email", "status": "sent"}


def dispatch_notifications(
    report: Dict[str, Any],
    session: str = "daily",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """格式化簡報並推送至所有已設定管道；同時保存純文字與 LINE Flex 卡片 JSON 供檢查。"""
    brief = format_push_brief(report, session=session)
    flex_payload = build_line_flex_message(report, session=session)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    msg_file: Path = OUTPUT_DIR / "last_push_message.txt"
    flex_file: Path = OUTPUT_DIR / "last_line_flex.json"
    msg_file.write_text(brief, encoding="utf-8")
    flex_file.write_text(json.dumps(flex_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    results: List[Dict[str, Any]] = []
    if dry_run:
        results.append(
            {
                "channel": "dry_run",
                "status": "preview_only",
                "saved_text": str(msg_file),
                "saved_line_flex": str(flex_file),
            }
        )
    else:
        for fn in (
            lambda: _send_line(brief, report, session),
            lambda: _send_telegram(brief),
            lambda: _send_discord(brief, report, session),
            lambda: _send_email(brief, session),
        ):
            try:
                results.append(fn())
            except Exception as exc:
                results.append({"channel": "error", "status": "failed", "reason": str(exc)})

    return {
        "session": session,
        "saved_to": str(msg_file),
        "saved_line_flex": str(flex_file),
        "brief": brief,
        "results": results,
    }
