#!/usr/bin/env python3
"""
Stock Intel 智策股市情報與多空推演系統 — 命令列統一入口

用法：
  python3 run.py analyze                                  # 全球多語新聞＋台股三大法人＋策略回測，匯出報告
  python3 run.py stock 2330                               # 即時單股診斷（基本面＋技術面＋三大法人＋回測）
  python3 run.py backtest NVDA                            # 獨立檢視單股 2 年期 3 大量化策略回測明細
  python3 run.py push --session tw_premarket --dry-run    # 預覽或發送盤前投資決策推播簡報
  python3 run.py schedule                                 # 啟動每日台股 (08:15) & 美股 (20:45) 盤前自動排程
  python3 run.py serve --port 8080                        # 啟動互動式網頁儀表板伺服器
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from stock_intel.analyzers.pipeline import StockIntelPipeline
from stock_intel.config import OUTPUT_DIR
from stock_intel.notifications.notifier import dispatch_notifications, verify_line_bot
from stock_intel.scheduler import execute_session, run_scheduler_loop
from stock_intel.storage.cache import ReportStore
from stock_intel.web.report_exporter import export_markdown_report, export_standalone_html


def _print_macro_summary(report_dict: dict) -> None:
    macro = report_dict["macro"]
    print("\n" + "=" * 78)
    print("  智策股市情報與多空推演系統 v2.0 (全球跨語系 × 三大法人 × 策略回測)")
    print("=" * 78)
    print(f"產出時間 (UTC): {report_dict['generated_at']}")
    print(f"資料狀態: {report_dict['data_mode']} | 推演引擎: {macro.get('analysis_engine', 'local_quant')}")
    print(
        f"整體大盤判定: 【{macro['stance']}】 "
        f"(綜合指數 {macro['overall_score']:+.1f} / 信心度 {macro['confidence']}%)"
    )
    print(
        f"分項分數 -> 全球新聞: {macro['news_sentiment_score']:+.1f} | "
        f"市場動能: {macro['market_momentum_score']:+.1f} | "
        f"風險環境: {macro['risk_index_score']:+.1f}"
    )

    reg_sum = macro.get("region_summary") or []
    if reg_sum:
        print("\n--- 全球各區域新聞情緒分布 ---")
        for r in reg_sum:
            print(f"  {r['region']:<8} | {r['news_count']:3d} 則 | 平均情緒 {r['avg_score']:+5.1f} ({r['direction']}) | {r['top_headline'][:42]}")

    tw_inst = macro.get("tw_institutional")
    if tw_inst:
        print(f"\n--- 台股大盤三大法人買賣超 ({tw_inst['date']}) ---")
        print(
            f"  外資 {tw_inst['foreign_net_billion']:+.2f} 億 | "
            f"投信 {tw_inst['trust_net_billion']:+.2f} 億 | "
            f"自營 {tw_inst['dealer_net_billion']:+.2f} 億 | "
            f"合計 {tw_inst['total_net_billion']:+.2f} 億  [{tw_inst['signal']}]"
        )

    bull_secs = report_dict.get("bullish_sectors") or report_dict["sectors"][:4]
    bear_secs = report_dict.get("bearish_sectors") or list(reversed(report_dict["sectors"]))[:4]

    print("\n--- ▲ 產業利多／抗跌推薦排行（含消息面要素）---")
    for idx, sec in enumerate(bull_secs, 1):
        print(
            f"  {idx}. {sec['name']:<14} | 評分 {sec['score']:5.1f} ({sec['outlook_label']}) "
            f"| 新聞 {sec['news_score']:+5.1f} | 總經 {sec['macro_tailwind_score']:+5.1f}"
        )
        if sec.get("news_summary_reason"):
            print(f"     └ {sec['news_summary_reason'][:92]}")

    print("\n--- ▼ 產業利空／警戒避開排行（含消息面事由）---")
    for idx, sec in enumerate(bear_secs, 1):
        print(
            f"  {idx}. {sec['name']:<14} | 評分 {sec['score']:5.1f} ({sec['outlook_label']}) "
            f"| 新聞 {sec['news_score']:+5.1f} | 總經 {sec['macro_tailwind_score']:+5.1f}"
        )
        bear_n = sec.get("bearish_catalysts_news") or []
        if bear_n:
            b0 = bear_n[0]
            print(f"     └ 【{b0['event_type']}】{b0['reason']}（{b0['source']}：{str(b0['title'])[:44]}）")
        elif sec.get("news_summary_reason"):
            print(f"     └ {sec['news_summary_reason'][:92]}")

    print("\n--- 跨市場重點個股 Top 8（含三大法人 & 2年期策略回測）---")
    for st in report_dict["stocks"][:8]:
        f = st["fundamental"]
        t = st["technical"]
        bt = st.get("backtest")
        inst = st.get("institutional")
        bt_txt = f"回測 {bt['best_total_return_pct']:+5.1f}% (勝率{bt['best_win_rate_pct']:4.1f}%)" if bt else "—"
        inst_txt = f"法人{inst['total_net_lots']:+,d}張" if inst else "美股"
        print(
            f"  {st['symbol']:<8} {st['name']:<14} | {st['rating']}({st['total_score']:4.1f}) "
            f"| 基本{f['grade']:<2} 技術{t['score']:4.1f} | {inst_txt:<12} | {bt_txt}"
        )

    cr = report_dict.get("credit_radar")
    if cr:
        print(
            f"\n--- AI 信用風險雷達 | 系統性指數 {cr['systemic_score']:.1f}/100 "
            f"[{cr['risk_level']}・{cr['spread_regime']}] ---"
        )
        print(f"  {cr['ai_summary']}")
        for w in (cr.get("watchlist") or [])[:4]:
            print(
                f"  警戒 {w['symbol']:<8} {w['name']:<12} | 信評 {w['credit_rating']:<3} "
                f"風險 {w['risk_score']:4.1f} ({w['risk_level']}) | {str(w['top_flag'])[:48]}"
            )
    print("=" * 78)


def cmd_analyze(args: argparse.Namespace) -> int:
    print("正在併發蒐集全球 7 大區域多語系新聞、跨市場指數、台股三大法人買賣超與 2 年期個股回測資料...")
    pipeline = StockIntelPipeline()
    report = pipeline.run_full_analysis(save_to_db=True)
    report_dict = report.to_dict()
    _print_macro_summary(report_dict)

    out_dir = Path(args.out_dir) if args.out_dir else OUTPUT_DIR
    md_path = export_markdown_report(report_dict, out_dir / "latest_report.md")
    html_path = export_standalone_html(report_dict, out_dir / "latest_dashboard.html")
    print(f"\n已匯出 Markdown 投研報告：{md_path}")
    print(f"已匯出互動式離線 HTML 儀表板：{html_path}\n")
    return 0


def cmd_stock(args: argparse.Namespace) -> int:
    print(f"正在抓取 {args.symbol} 2 年日線、財報、三大法人籌碼並執行策略回測...")
    pipeline = StockIntelPipeline()
    st = pipeline.analyze_single_stock(args.symbol)
    if st is None:
        print(f"錯誤：無法取得 {args.symbol} 的市場資料，請確認股票代號是否正確。", file=sys.stderr)
        return 1

    f = st.fundamental
    t = st.technical
    inst = st.institutional
    bt = st.backtest

    print("\n" + "=" * 78)
    print(f"  {st.name} ({st.symbol} / {st.market}) — {st.rating}（綜合評分 {st.total_score:.1f}）")
    print("=" * 78)
    print(f"產業分類：{st.sector_name} | 角色：{st.role}")
    print(
        f"最新報價：{t.price:.2f} {f.currency} | 1日 {t.change_pct_1d:+.2f}% | "
        f"5日 {t.change_pct_5d:+.2f}% | 20日 {t.change_pct_20d:+.2f}% | 60日 {t.change_pct_60d:+.2f}%"
    )
    print(
        f"基本面：{f.grade} ({f.score:.1f}分) | PE={f.pe_ratio} | FwdPE={f.forward_pe} | "
        f"PB={f.pb_ratio} | ROE={f.roe_pct}% | 毛利率={f.gross_margin_pct}% | 殖利率={f.dividend_yield_pct}%"
    )
    if f.twse_monthly_rev_yoy_pct is not None:
        print(
            f"TWSE 月營收 ({f.twse_rev_period})：月增 {f.twse_monthly_rev_mom_pct}% | "
            f"年增 {f.twse_monthly_rev_yoy_pct}% | 累計年增 {f.twse_cum_rev_yoy_pct}%"
        )
    print(
        f"技術面：{t.trend_label} ({t.score:.1f}分) | MA5={t.ma5} | MA20={t.ma20} | MA60={t.ma60} | "
        f"RSI(14)={t.rsi14} | MACD柱={t.macd_hist} | 支撐={t.support_level} | 壓力={t.resistance_level}"
    )

    if inst:
        print(
            f"\n【台股三大法人籌碼 ({inst.date})】{inst.signal} ({inst.score:.1f}分) -> "
            f"外資 {inst.foreign_net_lots:+,d} 張 | 投信 {inst.trust_net_lots:+,d} 張 | "
            f"自營 {inst.dealer_net_lots:+,d} 張 | 合計 {inst.total_net_lots:+,d} 張"
        )
        for p in inst.pros:
            print(f"  + {p}")
        for c in inst.cons:
            print(f"  - {c}")

    if bt:
        print(f"\n【量化策略回測 ({bt['start_date']} ~ {bt['end_date']}，共 {bt['trading_days']} 交易日 | {bt['fee_model']})】")
        print(
            f"  買進持有基準：總報酬 {bt['benchmark_return_pct']:+.2f}% | "
            f"年化 {bt['benchmark_cagr_pct']:+.2f}% | 最大回撤 {bt['benchmark_max_drawdown_pct']:.2f}% | 夏普 {bt['benchmark_sharpe']:.2f}"
        )
        for s in bt["strategies"]:
            mark = "★" if s["id"] == bt["best_strategy_id"] else " "
            print(
                f" {mark} {s['name']:<26} | 報酬 {s['total_return_pct']:+6.2f}% (Alpha {s['alpha_pct']:+6.2f}%) "
                f"| 年化 {s['cagr_pct']:+6.2f}% | 回撤 {s['max_drawdown_pct']:6.2f}% | 夏普 {s['sharpe_ratio']:4.2f} "
                f"| 勝率 {s['win_rate_pct']:4.1f}% ({s['trade_count']}次) | 現況:{s['current_signal']}"
            )

    print("\n【基本面優勢 / 劣勢】")
    for p in f.pros:
        print(f"  + {p}")
    for c in f.cons:
        print(f"  - {c}")
    print("\n【技術面優勢 / 劣勢】")
    for p in t.pros:
        print(f"  + {p}")
    for c in t.cons:
        print(f"  - {c}")
    print("=" * 78 + "\n")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    return cmd_stock(args)


def cmd_push(args: argparse.Namespace) -> int:
    res = execute_session(session=args.session, dry_run=args.dry_run)
    print("\n--- 推播簡報內容預覽 ---")
    print(res["brief"])
    print(f"\n已保存純文字簡報至：{res['saved_to']}")
    print(f"已保存 LINE Flex 卡片 JSON 至：{res['saved_line_flex']}")
    return 0


def cmd_test_line(args: argparse.Namespace) -> int:
    report = ReportStore().load_latest()
    if args.send and report is None:
        print("尚未有快取報告，正在先執行一次快速全球分析...")
        report = StockIntelPipeline().run_full_analysis(save_to_db=True).to_dict()
    res = verify_line_bot(send_test=args.send, report=report)
    if not res.get("ok"):
        print(f"LINE 驗證未通過：{res.get('error')}")
        return 1
    print(f"LINE 官方帳號連線成功：{res.get('bot_name')} ({res.get('basic_id')})")
    print(f"推播模式：{res.get('mode')}")
    if args.send:
        print(f"測試卡片發送結果：{res.get('push_result')}")
    else:
        print("提示：加上 --send 參數即可立即發送一張測試 Flex 投資卡片到您的 LINE。")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    if args.run_now:
        res = execute_session(session=args.run_now, dry_run=args.dry_run)
        print("\n" + res["brief"])
        return 0
    try:
        run_scheduler_loop(dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n排程器已安全停止。")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    host = args.host or os.getenv("HOST", "0.0.0.0")
    port = args.port or int(os.getenv("PORT", "8080"))
    print(f"啟動 Stock Intel 網頁儀表板：http://{host}:{port}")
    uvicorn.run("stock_intel.web.server:app", host=host, port=port, reload=args.reload)
    return 0


def cmd_watchlist(args: argparse.Namespace) -> int:
    store = ReportStore()
    action = args.action
    if action == "list":
        items = store.list_watchlist()
        if not items:
            print("目前尚無自選股，請執行：python3 run.py watchlist add NVDA 2330 --note \"長線觀察\"")
            return 0
        print(f"\n--- 我的自選股清單（共 {len(items)} 檔）---")
        for it in items:
            note_txt = f" | 備忘：{it['note']}" if it.get("note") else ""
            print(f"  ★ {it['symbol']:<10} {it['name']:<14} [{it['market']}]{note_txt}")
        print()
        return 0
    if action == "add":
        if not args.symbols:
            print("請提供至少一個股票代號，例如：python3 run.py watchlist add 2330 NVDA", file=sys.stderr)
            return 1
        pipeline = StockIntelPipeline(store=store)
        for raw in args.symbols:
            sym, mkt = pipeline.collector.normalize_symbol(raw)
            st = pipeline.analyze_single_stock(raw)
            name = st.name if st else sym
            if st:
                sym, mkt = st.symbol, st.market
            saved = store.add_watchlist(sym, name=name, market=mkt, note=args.note or "")
            print(f"已加入自選股：★ {saved['symbol']} ({saved['name']} / {saved['market']})")
        return 0
    if action == "remove":
        if not args.symbols:
            print("請提供要移除的股票代號，例如：python3 run.py watchlist remove NVDA", file=sys.stderr)
            return 1
        pipeline = StockIntelPipeline(store=store)
        for raw in args.symbols:
            sym, _ = pipeline.collector.normalize_symbol(raw)
            ok = store.remove_watchlist(raw) or store.remove_watchlist(sym)
            print(f"{'已移除自選股' if ok else '自選股清單中找不到'}：{sym}")
        return 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="stock-intel",
        description="智策股市情報與多空推演系統（全球多語新聞、三大法人籌碼、AI信用風險雷達、自選股追蹤與策略回測）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_an = sub.add_parser("analyze", help="執行全球新聞＋跨市場分析＋三大法人＋回測，匯出報告")
    p_an.add_argument("--out-dir", help="報告輸出目錄（預設為 ./reports）")
    p_an.set_defaults(func=cmd_analyze)

    p_st = sub.add_parser("stock", help="即時分析單一美股或台股（含基本面、技術面、三大法人與回測）")
    p_st.add_argument("symbol", help="股票代號，例如 NVDA、AAPL、2330、2330.TW")
    p_st.set_defaults(func=cmd_stock)

    p_wl = sub.add_parser("watchlist", help="管理個人美台股自選股清單（list / add / remove）")
    p_wl.add_argument("action", choices=["list", "add", "remove"], help="操作：list | add | remove")
    p_wl.add_argument("symbols", nargs="*", help="股票代號，例如 2330 NVDA TSLA")
    p_wl.add_argument("--note", default="", help="個人投資備忘（如目標價、觀察重點）")
    p_wl.set_defaults(func=cmd_watchlist)

    p_bt = sub.add_parser("backtest", help="執行單股 2 年期 3 大量化策略回測")
    p_bt.add_argument("symbol", help="股票代號，例如 2330 或 NVDA")
    p_bt.set_defaults(func=cmd_backtest)

    p_pu = sub.add_parser("push", help="立即執行一次分析並發送盤前投資決策推播")
    p_pu.add_argument("--session", default="tw_premarket", choices=["tw_premarket", "us_premarket", "daily"])
    p_pu.add_argument("--dry-run", action="store_true", help="僅預覽推播內容與 LINE Flex 卡片，不實際發送")
    p_pu.set_defaults(func=cmd_push)

    p_ln = sub.add_parser("test-line", help="驗證 LINE Channel Access Token 並測試發送 Flex 卡片")
    p_ln.add_argument("--send", action="store_true", help="驗證後立刻發送一張盤前 Flex 卡片測試訊息")
    p_ln.set_defaults(func=cmd_test_line)

    p_sc = sub.add_parser("schedule", help="啟動每日台股 (08:15) 與美股 (20:45) 台北時間盤前排程")
    p_sc.add_argument("--run-now", choices=["tw_premarket", "us_premarket", "daily"], help="立刻執行指定場次一次後結束")
    p_sc.add_argument("--dry-run", action="store_true", help="乾跑模式（僅產生簡報與報告，不推播外部管道）")
    p_sc.set_defaults(func=cmd_schedule)

    p_sv = sub.add_parser("serve", help="啟動 FastAPI 互動式網頁儀表板伺服器")
    p_sv.add_argument("--host", default=None, help="監聽主機（預設 0.0.0.0）")
    p_sv.add_argument("--port", type=int, default=None, help="連接埠（預設 8080）")
    p_sv.add_argument("--reload", action="store_true", help="啟用開發熱重載模式")
    p_sv.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
