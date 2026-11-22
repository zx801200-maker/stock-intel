"""報告匯出模組：產出含全球區域情緒、台股三大法人籌碼與策略回測之 Markdown 與離線 HTML 儀表板。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from stock_intel.config import OUTPUT_DIR

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _fmt(val: Any, suffix: str = "", digits: int = 2) -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):.{digits}f}{suffix}"
    except Exception:
        return str(val)


def export_markdown_report(report: Dict[str, Any], out_path: Path | None = None) -> Path:
    """產出結構化繁體中文 Markdown 每日投資研究報告。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = out_path or (OUTPUT_DIR / "latest_report.md")

    macro = report["macro"]
    sectors = report.get("sectors") or []
    stocks = report.get("stocks") or []

    lines = [
        "# 智策股市情報與多空推演報告（全球跨語系 × 三大法人 × 策略回測）",
        "",
        f"- **產出時間 (UTC)**：`{report['generated_at']}`",
        f"- **資料模式**：`{report['data_mode']}` | **推演引擎**：`{macro.get('analysis_engine', 'local_quant')}`",
        f"- **全球情報則數**：{report['news_count']} 則（多語系跨洲覆蓋） | **深度剖析個股**：{report['stocks_analyzed']} 檔（美股 + 台股）",
        "",
        "## 一、全球情勢與大盤多空推演",
        "",
        f"**整體判定：{macro['stance']}**（綜合多空分數：`{macro['overall_score']:+.1f}` / 信心度：`{macro['confidence']}%`）",
        "",
        f"> {macro['executive_summary']}",
        "",
    ]

    if macro.get("llm_commentary"):
        lines.extend(["### AI 策略師深度解讀", "", macro["llm_commentary"], ""])

    # 全球各區域新聞情緒表
    reg_sum = macro.get("region_summary") or []
    if reg_sum:
        lines.extend([
            "### 全球各區域財經新聞情緒分布",
            "",
            "| 區域板塊 | 新聞則數 | 平均情緒分數 | 方向 | 代表焦點頭條 |",
            "|---|---:|---:|---|---|",
        ])
        for r in reg_sum:
            lines.append(
                f"| **{r['region']}** | {r['news_count']} | {r['avg_score']:+.1f} | {r['direction']} | {r['top_headline']} |"
            )
        lines.append("")

    # 台股三大法人大盤買賣超
    tw_inst = macro.get("tw_institutional")
    if tw_inst:
        lines.extend([
            f"### 台股大盤三大法人買賣超統計（{tw_inst['date']}）",
            "",
            f"- **籌碼訊號**：`{tw_inst['signal']}` — {tw_inst['summary']}",
            f"- **外資及陸資**：`{tw_inst['foreign_net_billion']:+.2f}` 億元 ｜ **投信**：`{tw_inst['trust_net_billion']:+.2f}` 億元 ｜ **自營商**：`{tw_inst['dealer_net_billion']:+.2f}` 億元 ｜ **合計**：`{tw_inst['total_net_billion']:+.2f}` 億元",
            "",
        ])

    lines.extend([
        "### 全球跨市場關鍵指數快照",
        "",
        "| 指標 | 類別 | 最新報價 | 1日漲跌 | 5日漲跌 | 1月漲跌 | 訊號 |",
        "|---|---|---:|---:|---:|---:|---|",
    ])
    for b in macro.get("benchmarks") or []:
        lines.append(
            f"| {b['name']} (`{b['symbol']}`) | {b['category']} | {b['price']:.2f} "
            f"| {b['change_pct_1d']:+.2f}% | {b['change_pct_5d']:+.2f}% | {b['change_pct_1m']:+.2f}% | {b['signal']} |"
        )

    lines.extend(["", "### 主要利多催化劑", ""])
    for item in macro.get("bullish_catalysts") or []:
        lines.append(f"- {item}")

    lines.extend(["", "### 主要利空風險", ""])
    for item in macro.get("bearish_risks") or []:
        lines.append(f"- {item}")

    lines.extend(["", "### 操作策略建議", ""])
    for item in macro.get("action_plan") or []:
        lines.append(f"- {item}")

    cr = report.get("credit_radar")
    if cr:
        lines.extend([
            "",
            "## 附錄：AI 信用風險雷達（債市利差 × 企業五維信用壓力）",
            "",
            f"**系統性信用風險總指數：`{cr['systemic_score']:.1f} / 100`（{cr['risk_level']}・{cr['spread_regime']}）**",
            "",
            f"> {cr['ai_summary']}",
            "",
            "| 標的 | 市場 | AI模擬信評 | 信用風險指數 | 燈號 | 核心紅旗警示 |",
            "|---|---|---|---:|---|---|",
        ])
        for w in (cr.get("watchlist") or [])[:8]:
            lines.append(
                f"| **{w['name']}** (`{w['symbol']}`) | {w['market']} | `{w['credit_rating']}` "
                f"| {w['risk_score']:.1f} | {w['risk_level']} | {w['top_flag']} |"
            )

    bull_secs = report.get("bullish_sectors") or sectors[:4]
    bear_secs = report.get("bearish_sectors") or list(reversed(sectors))[:4]

    lines.extend([
        "",
        "## 二、產業推薦與警戒排行（含消息面合約／官方公告／事件歸因）",
        "",
        "### ▲ 產業利多／抗跌推薦排行",
        "",
        "| 排名 | 產業 | 評分 | 判定 | 新聞情緒 | 總經順風 | 消息面利多事由（合約／公告／催化） |",
        "|---:|---|---:|---|---:|---:|---|",
    ])
    for idx, s in enumerate(bull_secs, 1):
        reason = s.get("news_summary_reason") or (s["key_drivers"][0] if s.get("key_drivers") else "—")
        lines.append(
            f"| {idx} | **{s['name']}** | {s['score']:.1f} | {s['outlook_label']} "
            f"| {s['news_score']:+.1f} | {s['macro_tailwind_score']:+.1f} | {reason} |"
        )

    lines.extend([
        "",
        "### ▼ 產業利空／警戒避開排行",
        "",
        "| 警戒序 | 產業 | 評分 | 判定 | 新聞情緒 | 總經逆風 | 消息面利空事由（調查／事件／衝擊） |",
        "|---:|---|---:|---|---:|---:|---|",
    ])
    for idx, s in enumerate(bear_secs, 1):
        bear_n = s.get("bearish_catalysts_news") or []
        if bear_n:
            b0 = bear_n[0]
            reason = f"【{b0['event_type']}】{b0['reason']}（{b0['macro_region']}・{b0['source']}：「{str(b0['title'])[:48]}」）"
        else:
            reason = s.get("news_summary_reason") or (s["key_risks"][0] if s.get("key_risks") else "—")
        lines.append(
            f"| {idx} | **{s['name']}** | {s['score']:.1f} | {s['outlook_label']} "
            f"| {s['news_score']:+.1f} | {s['macro_tailwind_score']:+.1f} | {reason} |"
        )

    lines.extend([
        "",
        "## 三、重點個股基本面 × 技術面 × 籌碼 × 策略回測剖析（Top 12）",
        "",
    ])
    for st in stocks[:12]:
        f = st["fundamental"]
        t = st["technical"]
        inst = st.get("institutional")
        bt = st.get("backtest")

        lines.extend([
            f"### {st['name']} (`{st['symbol']}` / {st['market']}) — {st['rating']}（綜合 {st['total_score']:.1f} 分）",
            "",
            f"- **所屬產業**：{st['sector_name']}（{st['role']}）",
            f"- **最新股價**：{t['price']:.2f} {f['currency']}（1日 {t['change_pct_1d']:+.2f}% / 20日 {t['change_pct_20d']:+.2f}%）",
            f"- **基本面**：`{f['grade']}`（{f['score']:.1f} 分）｜ PE: {_fmt(f['pe_ratio'], 'x', 1)} ｜ ROE: {_fmt(f['roe_pct'], '%', 1)} ｜ 毛利率: {_fmt(f['gross_margin_pct'], '%', 1)} ｜ 殖利率: {_fmt(f['dividend_yield_pct'], '%', 2)}"
            + (f" ｜ TWSE月營收YoY: {_fmt(f['twse_monthly_rev_yoy_pct'], '%', 1)}" if f.get("twse_monthly_rev_yoy_pct") is not None else ""),
            f"- **技術面**：`{t['trend_label']}`（{t['score']:.1f} 分）｜ MA20: {_fmt(t['ma20'])} ｜ MA60: {_fmt(t['ma60'])} ｜ RSI(14): {_fmt(t['rsi14'], '', 1)} ｜ 支撐/壓力: {_fmt(t['support_level'])} / {_fmt(t['resistance_level'])}",
        ])
        if inst:
            lines.append(
                f"- **台股三大法人 ({inst['date']})**：`{inst['signal']}`（{inst['score']:.1f} 分）｜ "
                f"外資 `{inst['foreign_net_lots']:+,d}` 張 ｜ 投信 `{inst['trust_net_lots']:+,d}` 張 ｜ "
                f"自營 `{inst['dealer_net_lots']:+,d}` 張 ｜ 合計 `{inst['total_net_lots']:+,d}` 張"
            )
        if bt:
            lines.append(
                f"- **策略回測 ({bt['start_date']} ~ {bt['end_date']})**：最佳策略「{bt['best_strategy_name']}」"
                f"總報酬 `{bt['best_total_return_pct']:+.1f}%`（對買進持有超額 Alpha `{bt['best_alpha_pct']:+.1f}%`、"
                f"最大回撤 `{bt['best_max_drawdown_pct']:.1f}%`、夏普 `{bt['best_sharpe']:.2f}`、勝率 `{bt['best_win_rate_pct']:.1f}%`、"
                f"當前訊號 `{bt['best_current_signal']}`）"
            )

        lines.extend(["", "**基本面優勢 / 劣勢：**"])
        for p in (f.get("pros") or [])[:3]:
            lines.append(f"- [+] {p}")
        for c in (f.get("cons") or [])[:3]:
            lines.append(f"- [-] {c}")

        lines.extend(["", "**技術面優勢 / 劣勢：**"])
        for p in (t.get("pros") or [])[:3]:
            lines.append(f"- [+] {p}")
        for c in (t.get("cons") or [])[:3]:
            lines.append(f"- [-] {c}")
        lines.append("")

    lines.extend(["---", "", f"*{report.get('disclaimer', '')}*"])
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def export_standalone_html(report: Dict[str, Any], out_path: Path | None = None) -> Path:
    """將儀表板 HTML/CSS/JS 與即時資料打包為單一可離線雙擊開啟的 HTML 報告檔。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = out_path or (OUTPUT_DIR / "latest_dashboard.html")

    html_src = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    css_src = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    js_src = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    data_json = json.dumps(report, ensure_ascii=False).replace("</script>", "<\\/script>")
    inlined = html_src.replace(
        '<link rel="stylesheet" href="/static/styles.css" />',
        f"<style>\n{css_src}\n</style>",
    ).replace(
        '<script src="/static/app.js"></script>',
        f"<script>window.__INITIAL_REPORT__ = {data_json};</script>\n<script>\n{js_src}\n</script>",
    )
    target.write_text(inlined, encoding="utf-8")
    return target
