"""核心引擎單元測試：驗證全球多語情緒分析、台股三大法人籌碼、2年期策略回測、技術指標與基本面評分。"""

from __future__ import annotations

import math
import unittest

from stock_intel.analyzers.backtester import run_stock_backtest
from stock_intel.analyzers.fundamental import analyze_fundamentals
from stock_intel.analyzers.institutional import (
    analyze_tw_market_institutional,
    analyze_tw_stock_institutional,
)
from stock_intel.analyzers.sentiment_engine import (
    deduce_macro_outlook,
    rank_sectors,
    score_news_items,
)
from stock_intel.analyzers.technical import analyze_technicals
from stock_intel.models import BenchmarkQuote, NewsItem


class TestStockIntelAnalyzers(unittest.TestCase):
    def test_multilingual_global_sentiment_and_regions(self) -> None:
        items = [
            NewsItem(
                id="us1",
                title="NVIDIA surges to record high as AI data center demand booms",
                summary="Hyperscalers raise capex guidance for GPU clusters.",
                link="",
                source="CNBC",
                region="美國/華爾街",
                macro_region="北美",
                lang="en",
                published_at="2026-11-21T00:00:00+00:00",
            ),
            NewsItem(
                id="de1",
                title="Befreiungsschlag: Bayer-Aktie steigt nach starkem Gewinn",
                summary="",
                link="",
                source="Google DE",
                region="德國/歐元區",
                macro_region="歐洲",
                lang="de",
                published_at="2026-11-21T00:00:00+00:00",
            ),
            NewsItem(
                id="kr1",
                title="한국 반도체 수출 둔화 및 글로벌 관세 압박 우려",
                summary="",
                link="",
                source="Google KR",
                region="韓國/韓股",
                macro_region="韓國",
                lang="ko",
                published_at="2026-11-21T00:00:00+00:00",
            ),
            NewsItem(
                id="jp1",
                title="日銀利上げ懸念で半導体株が急落",
                summary="",
                link="",
                source="Google JP",
                region="日本/日股",
                macro_region="日本",
                lang="ja",
                published_at="2026-11-21T00:00:00+00:00",
            ),
        ]
        scored = score_news_items(items)
        self.assertGreater(scored[0].sentiment_score, 0.35)
        self.assertGreater(scored[1].sentiment_score, 0.35)
        self.assertIn("healthcare_bio", scored[1].matched_sectors)
        self.assertLess(scored[2].sentiment_score, -0.35)
        self.assertIn("ai_semis", scored[2].matched_sectors)
        self.assertLess(scored[3].sentiment_score, -0.35)
        self.assertIn("ai_semis", scored[3].matched_sectors)

    def test_tw_institutional_market_and_stock(self) -> None:
        m = analyze_tw_market_institutional(
            {
                "date": "2026-11-20",
                "foreign_net_billion": -95.11,
                "trust_net_billion": -73.47,
                "dealer_net_billion": -340.83,
                "total_net_billion": -509.41,
            }
        )
        self.assertIsNotNone(m)
        self.assertEqual(m.signal, "法人大賣")

        st_bull = analyze_tw_stock_institutional(
            {
                "date": "2026-11-20",
                "foreign_net_lots": 3500,
                "trust_net_lots": 820,
                "dealer_net_lots": 120,
                "total_net_lots": 4440,
            }
        )
        self.assertIsNotNone(st_bull)
        self.assertEqual(st_bull.signal, "土洋合擊買超")
        self.assertGreaterEqual(st_bull.score, 80.0)

    def test_backtester_three_strategies(self) -> None:
        bars = []
        for i in range(260):
            # 模擬先漲後修正再反彈的真實波動走勢
            base = 100.0 + i * 0.25 + math.sin(i / 14.0) * 14.0
            bars.append(
                {
                    "date": f"2025-{(i // 22) % 12 + 1:02d}-{(i % 28) + 1:02d}",
                    "open": round(base - 0.6, 2),
                    "high": round(base + 1.8, 2),
                    "low": round(base - 1.5, 2),
                    "close": round(base + 0.4, 2),
                    "volume": 1_500_000 + (i % 7) * 120_000,
                }
            )
        bt = run_stock_backtest({"bars": bars}, market="TW")
        self.assertIsNotNone(bt)
        self.assertEqual(len(bt["strategies"]), 3)
        self.assertGreater(bt["trading_days"], 150)
        for strat in bt["strategies"]:
            self.assertTrue(len(strat["equity_curve"]) >= 10)
            self.assertIn(strat["current_signal"], ("持有偏多", "空手觀望"))

    def test_macro_deduction_and_sector_ranking(self) -> None:
        items = score_news_items(
            [
                NewsItem(
                    id="a",
                    title="Fed signals rate cuts as inflation cools, tech stocks rally",
                    summary="Strong AI chip earnings boost semiconductor optimism.",
                    link="",
                    source="CNBC",
                    region="美國/華爾街",
                    macro_region="北美",
                    lang="en",
                    published_at="2026-11-21T00:00:00+00:00",
                )
            ]
        )
        benchmarks = [
            BenchmarkQuote("^GSPC", "S&P 500", "美股大盤", 6000.0, 1.2, 3.0, 5.0, False, "偏多支撐"),
            BenchmarkQuote("^VIX", "VIX", "波動避險", 13.5, -5.0, -10.0, -12.0, True, "偏多支撐"),
        ]
        macro, intensity = deduce_macro_outlook(items, benchmarks)
        self.assertGreater(macro.overall_score, 20)
        self.assertEqual(len(macro.region_summary), 1)

        sectors = rank_sectors(items, intensity, {"ai_semis": [60.0]}, {"ai_semis": [85.0]})
        self.assertEqual(sectors[0].sector_id, "ai_semis")

    def test_technical_and_fundamental(self) -> None:
        bars = [
            {
                "date": f"2026-09-{(i % 28) + 1:02d}",
                "open": 100.0 + i * 0.7,
                "high": 102.0 + i * 0.7,
                "low": 99.0 + i * 0.7,
                "close": 101.0 + i * 0.7,
                "volume": 1000000 + i * 10000,
            }
            for i in range(80)
        ]
        tech = analyze_technicals({"bars": bars, "fifty_two_week_high": bars[-1]["high"]})
        self.assertGreaterEqual(tech.score, 65.0)

        fund = analyze_fundamentals(
            {
                "pe_ratio": 18.5,
                "forward_pe": 14.0,
                "pb_ratio": 4.2,
                "dividend_yield_pct": 2.4,
                "roe_pct": 32.0,
                "gross_margin_pct": 58.0,
                "profit_margin_pct": 38.0,
                "debt_to_equity": 35.0,
                "free_cash_flow": 5_000_000_000,
                "twse_monthly_rev_yoy_pct": 38.5,
                "twse_cum_rev_yoy_pct": 31.2,
                "twse_rev_period": "11510",
                "currency": "TWD",
                "data_source": "yahoo+twse",
            },
            current_price=1000.0,
            market="TW",
        )
        self.assertGreaterEqual(fund.score, 80.0)

    def test_line_flex_message_builder(self) -> None:
        from stock_intel.notifications.notifier import build_line_flex_message

        sample_report = {
            "generated_at": "2026-11-22T01:30:00+00:00",
            "news_count": 240,
            "macro": {
                "overall_score": -48.5,
                "stance": "警戒利空",
                "confidence": 92,
                "region_summary": [{"region": "北美", "avg_score": -16.0}, {"region": "台灣", "avg_score": -39.0}],
                "benchmarks": [{"symbol": "^TWII", "price": 36033.3, "change_pct_1d": -6.2, "change_pct_5d": -17.5, "invert_sentiment": False}],
                "tw_institutional": {
                    "date": "2026-11-20",
                    "foreign_net_billion": -95.1,
                    "trust_net_billion": -73.5,
                    "dealer_net_billion": -340.8,
                    "total_net_billion": -509.4,
                },
                "action_plan": ["防禦優先、保留現金彈性。"],
            },
            "sectors": [{"name": "醫療保健與生技製藥", "score": 55.7, "outlook_label": "溫和利多"}],
            "stocks": [
                {
                    "symbol": "2330.TW",
                    "name": "台積電",
                    "market": "TW",
                    "rating": "逢低觀察",
                    "total_score": 50.1,
                    "fundamental": {"grade": "A+"},
                    "technical": {"price": 2000.0, "change_pct_1d": -4.76, "trend_label": "空頭排列"},
                    "institutional": {"total_net_lots": -10901},
                    "backtest": {"best_total_return_pct": 66.7, "best_win_rate_pct": 40.0, "best_current_signal": "空手觀望"},
                }
            ],
            "news": [{"title": "AI tech rout hits global markets", "macro_region": "北美", "sentiment_label": "利空"}],
        }
        flex = build_line_flex_message(sample_report, session="tw_premarket")
        self.assertEqual(flex["type"], "flex")
        self.assertLessEqual(len(flex["altText"]), 400)
        self.assertEqual(flex["contents"]["type"], "bubble")
        self.assertIn("header", flex["contents"])
        self.assertIn("body", flex["contents"])
        self.assertIn("footer", flex["contents"])

    def test_event_catalyst_and_dual_sector_split(self) -> None:
        from stock_intel.analyzers.sentiment_engine import split_sector_recommendations

        items = [
            NewsItem(
                id="ev_bull",
                title="Lockheed Martin wins $2.5B defense contract with Pentagon",
                summary="Official contract deal expands aerospace backlog.",
                link="",
                source="CNBC",
                region="美國/企業事件",
                macro_region="北美",
                lang="en",
                published_at="2026-11-21T00:00:00+00:00",
            ),
            NewsItem(
                id="ev_bear",
                title="Nvidia faces SEC probe and tighter US export control on AI chips",
                summary="Regulatory investigation weighs on semiconductor sector.",
                link="",
                source="Reuters",
                region="美國/企業事件",
                macro_region="北美",
                lang="en",
                published_at="2026-11-21T00:00:00+00:00",
            ),
        ]
        scored = score_news_items(items)
        self.assertEqual(scored[0].event_type, "合約/訂單/併購利多")
        self.assertGreater(scored[0].sentiment_score, 0.1)
        self.assertEqual(scored[1].event_type, "監管調查/出口管制/駁回")
        self.assertLess(scored[1].sentiment_score, -0.3)

        sectors = rank_sectors(scored, {"geopolitics": 0.6}, {"defense_aero": [40.0], "ai_semis": [-60.0]}, {"defense_aero": [80.0], "ai_semis": [70.0]})
        bull, bear = split_sector_recommendations(sectors, top_n=4)
        self.assertEqual(len(bull), 4)
        self.assertEqual(len(bear), 4)
        self.assertEqual(bull[0].sector_id, "defense_aero")
        self.assertTrue(len(bull[0].bullish_catalysts_news) >= 1)
        ai_sec = next(s for s in sectors if s.sector_id == "ai_semis")
        self.assertTrue(len(ai_sec.bearish_catalysts_news) >= 1)
        self.assertIn("監管調查/出口管制/駁回", ai_sec.news_summary_reason)

    def test_article_reader_ssrf_and_google_news(self) -> None:
        from stock_intel.collectors.article_reader import extract_article_content

        res_local = extract_article_content("http://127.0.0.1:8000/secret")
        self.assertFalse(res_local["ok"])
        self.assertIn("不安全", res_local["error"])

        res_gnews = extract_article_content("https://news.google.com/rss/articles/CBMiTestToken123")
        self.assertFalse(res_gnews["ok"])
        self.assertIn("Google News", res_gnews["note"])
        self.assertEqual(res_gnews["final_url"], "https://news.google.com/rss/articles/CBMiTestToken123")

    def test_ai_credit_risk_radar(self) -> None:
        from stock_intel.analyzers.credit_radar import (
            analyze_stock_credit_risk,
            build_credit_radar_report,
        )
        from stock_intel.models import FundamentalAnalysis, StockReport, TechnicalAnalysis

        # 模擬高槓桿、負自由現金流、高波動公司 vs 淨現金、高 FCF 穩健龍頭
        bars_vol = [
            {"date": f"2026-09-{(i % 28) + 1:02d}", "close": 100.0 * (0.95 if i % 2 else 1.04) * (1 - i * 0.008)}
            for i in range(65)
        ]
        bars_calm = [
            {"date": f"2026-09-{(i % 28) + 1:02d}", "close": 100.0 + i * 0.15}
            for i in range(65)
        ]

        risky = analyze_stock_credit_risk(
            symbol="DEBT",
            name="High Debt Corp",
            sector_id="cloud_servers",
            fundamentals={
                "debt_to_equity": 260.0,
                "current_ratio": 0.72,
                "quick_ratio": 0.55,
                "total_cash": 100_000_000,
                "total_debt": 2_500_000_000,
                "free_cash_flow": -300_000_000,
                "operating_cash_flow": -50_000_000,
                "ebitda": 400_000_000,
                "total_revenue": 1_000_000_000,
                "profit_margin_pct": -8.5,
                "beta": 2.1,
            },
            chart={"bars": bars_vol},
            related_news=[{"title": "Moody's cuts Debt Corp amid credit downgrade and cash burn", "sentiment_score": -0.8}],
            systemic_spread_stress=65.0,
        )
        safe = analyze_stock_credit_risk(
            symbol="SAFE",
            name="Net Cash Giant",
            sector_id="ai_semis",
            fundamentals={
                "debt_to_equity": 22.0,
                "current_ratio": 2.8,
                "quick_ratio": 2.4,
                "total_cash": 40_000_000_000,
                "total_debt": 10_000_000_000,
                "free_cash_flow": 25_000_000_000,
                "operating_cash_flow": 32_000_000_000,
                "ebitda": 45_000_000_000,
                "total_revenue": 90_000_000_000,
                "profit_margin_pct": 35.0,
                "beta": 0.9,
            },
            chart={"bars": bars_calm},
            related_news=[],
            systemic_spread_stress=30.0,
        )
        self.assertGreater(risky.risk_score, 68.0)
        self.assertIn(risky.credit_rating, ("B", "CCC"))
        self.assertLess(safe.risk_score, 26.0)
        self.assertIn(safe.credit_rating, ("AAA", "AA"))

        dummy_f = FundamentalAnalysis(score=70.0, grade="A")
        dummy_t = TechnicalAnalysis(score=50.0, trend_label="區間震盪", price=100.0, change_pct_1d=0.0, change_pct_5d=0.0, change_pct_20d=0.0, change_pct_60d=0.0)
        st_list = [
            StockReport("DEBT", "High Debt Corp", "US", "cloud_servers", "雲端", "測試", 40.0, "謹慎避開", "", 40.0, dummy_f, dummy_t, credit_risk=risky),
            StockReport("SAFE", "Net Cash Giant", "US", "ai_semis", "半導體", "測試", 80.0, "強力關注", "", 70.0, dummy_f, dummy_t, credit_risk=safe),
        ]
        news = [
            NewsItem("c1", "High yield credit spread widens as AI debt-laden cloud firm faces downgrade", "", "", "CNBC", "美國", "en", "2026-11-21", sentiment_score=-0.75, sentiment_label="利空"),
        ]
        proxies = [
            {"symbol": "HYG", "name": "HYG", "category": "高收益信用", "price": 76.0, "change_pct_1d": -0.8, "change_pct_5d": -2.1, "change_pct_1m": -3.5},
            {"symbol": "LQD", "name": "LQD", "category": "投資級信用", "price": 108.0, "change_pct_1d": -0.3, "change_pct_5d": -0.9, "change_pct_1m": -1.5},
            {"symbol": "IEF", "name": "IEF", "category": "無風險基準", "price": 95.0, "change_pct_1d": 0.2, "change_pct_5d": 0.4, "change_pct_1m": 0.8},
            {"symbol": "BKLN", "name": "BKLN", "category": "私募/槓桿信貸", "price": 20.5, "change_pct_1d": -0.5, "change_pct_5d": -1.5, "change_pct_1m": -2.2},
            {"symbol": "KRE", "name": "KRE", "category": "銀行體系信用", "price": 54.0, "change_pct_1d": -2.0, "change_pct_5d": -5.5, "change_pct_1m": -8.0},
        ]
        bms = [
            BenchmarkQuote("^TNX", "10Y", "利率", 4.9, 1.0, 2.0, 5.0, True, "偏空承壓"),
            BenchmarkQuote("^VIX", "VIX", "波動", 32.0, 10.0, 25.0, 40.0, True, "偏空承壓"),
        ]
        radar = build_credit_radar_report(news, bms, proxies, st_list, enrich_articles=False)
        self.assertGreater(radar.systemic_score, 55.0)
        self.assertEqual(radar.watchlist[0]["symbol"], "DEBT")
        self.assertEqual(len(radar.credit_news), 1)
        self.assertEqual(len(radar.dimensions), 5)

    def test_watchlist_crud_and_line_priority(self) -> None:
        import tempfile
        from pathlib import Path
        from stock_intel.notifications.notifier import _select_focus_stocks
        from stock_intel.storage.cache import ReportStore

        with tempfile.TemporaryDirectory() as td:
            store = ReportStore(db_path=Path(td) / "test.db")
            added = store.add_watchlist("2330.TW", name="台積電", market="TW", note="月線觀察")
            self.assertEqual(added["symbol"], "2330.TW")
            self.assertEqual(len(store.list_watchlist()), 1)

            self.assertTrue(store.update_watchlist_note("2330.TW", "目標價 2200"))
            self.assertEqual(store.list_watchlist()[0]["note"], "目標價 2200")

            sample = {
                "watchlist": store.list_watchlist(),
                "stocks": [
                    {"symbol": "NVDA", "market": "US", "total_score": 80},
                    {"symbol": "2317.TW", "market": "TW", "total_score": 70},
                    {"symbol": "2330.TW", "market": "TW", "total_score": 60},
                ],
            }
            focus = _select_focus_stocks(sample, "tw_premarket")
            self.assertEqual(focus[0]["symbol"], "2330.TW")

            self.assertTrue(store.remove_watchlist("2330.TW"))
            self.assertEqual(len(store.list_watchlist()), 0)

    def test_strict_stock_news_filter(self) -> None:
        from datetime import datetime, timedelta, timezone
        from stock_intel.analyzers.pipeline import _match_stock_news
        from stock_intel.collectors.news_collector import is_valid_stock_news

        now_iso = datetime.now(timezone.utc).isoformat()
        stale_iso = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()

        def mk(title: str, pub: str = now_iso, sectors: list[str] | None = None) -> NewsItem:
            return NewsItem(
                id="t",
                title=title,
                summary="",
                link="https://example.com",
                source="Test",
                region="美國",
                lang="en",
                published_at=pub,
                matched_sectors=sectors or [],
            )

        # 1. 報價頁 / SEO 預測頁 / 懶人包 / 散戶論壇 / 權證行情一律剔除
        self.assertFalse(is_valid_stock_news(mk("LLY Stock Quote Price and Forecast - CNN"), "LLY", "禮來 (Eli Lilly)"))
        self.assertFalse(is_valid_stock_news(mk("Microsoft Corporation (MSFT) stock price, news, quote & history"), "MSFT", "微軟"))
        self.assertFalse(is_valid_stock_news(mk("Exxon Stock Price Forecast. Should You Buy XOM?"), "XOM", "艾克森美孚"))
        self.assertFalse(is_valid_stock_news(mk("台達電（2308）做什麼？股價走勢圖與懶人包"), "2308.TW", "台達電"))
        self.assertFalse(is_valid_stock_news(mk("長榮(2603) 個股概覽 | 個股 - 股市 - CMoney"), "2603.TW", "長榮"))
        self.assertFalse(is_valid_stock_news(mk("2603 長榮 - 股價該硬了吧 - 股市爆料同學會 - CMoney"), "2603.TW", "長榮"))
        self.assertFalse(is_valid_stock_news(mk("長榮元大69購04 緩步升 - 經濟日報"), "2603.TW", "長榮"))

        # 2. 同名不同公司與泛用字詞誤判剔除
        self.assertFalse(is_valid_stock_news(mk("長榮航第3季大賺 載客率創新高"), "2603.TW", "長榮"))
        self.assertFalse(is_valid_stock_news(mk("Applied Materials beats Q4 semiconductor estimates"), "AAOI", "Applied Optoelectronics, Inc."))

        # 3. 超過有效天數的過期舊聞剔除
        self.assertFalse(is_valid_stock_news(mk("Nvidia launches new AI GPU architecture", pub=stale_iso), "NVDA", "輝達 (NVIDIA)"))

        # 4. 真實近期公司新聞通過
        self.assertTrue(is_valid_stock_news(mk("Nvidia stock plunges 14% after hyperscaler capex warning"), "NVDA", "輝達 (NVIDIA)"))
        self.assertTrue(is_valid_stock_news(mk("TSMC expands 2nm wafer capacity for AI clients"), "2330.TW", "台積電 (TSMC)"))
        self.assertTrue(is_valid_stock_news(mk("Applied Optoelectronics wins 800G transceiver order"), "AAOI", "Applied Optoelectronics, Inc."))

        # 5. _match_stock_news 絕不硬塞無關的同產業新聞
        sector_only_news = [
            mk("Global chipmakers brace for tariff pressures across Asia", sectors=["ai_semis"]),
            mk("Data center power demand surges in 2026", sectors=["ai_semis"]),
        ]
        self.assertEqual(_match_stock_news("NVDA", "輝達 (NVIDIA)", "ai_semis", sector_only_news), [])


if __name__ == "__main__":
    unittest.main()
