"""核心分析管線：整合全球多語系新聞、台股三大法人買賣超、產業排行、個股基本面/技術面與2年期策略回測。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from stock_intel.analyzers.backtester import run_stock_backtest
from stock_intel.analyzers.credit_radar import (
    analyze_stock_credit_risk,
    build_credit_radar_report,
    compute_systemic_spread_stress,
)
from stock_intel.analyzers.fundamental import analyze_fundamentals
from stock_intel.analyzers.institutional import (
    analyze_tw_market_institutional,
    analyze_tw_stock_institutional,
)
from stock_intel.analyzers.llm_advisor import enhance_with_llm
from stock_intel.analyzers.sentiment_engine import (
    deduce_macro_outlook,
    rank_sectors,
    score_news_items,
    split_sector_recommendations,
)
from stock_intel.analyzers.technical import analyze_technicals
from stock_intel.collectors.article_reader import enrich_sector_catalysts_content
from stock_intel.collectors.market_collector import MarketCollector
from stock_intel.collectors.news_collector import collect_news, collect_stock_news, is_valid_stock_news
from stock_intel.config import SECTORS, STOCK_LOOKUP
from stock_intel.models import MarketReport, NewsItem, StockReport
from stock_intel.storage.cache import ReportStore


def _rate_stock(total_score: float, fund_score: float, tech_score: float) -> str:
    if total_score >= 74 and fund_score >= 64:
        return "強力關注"
    if total_score >= 63:
        return "偏多布局"
    if fund_score >= 66 and tech_score < 50:
        return "逢低觀察"
    if total_score >= 48:
        return "中性觀望"
    return "謹慎避開"


def _summarize_stock(
    name: str,
    rating: str,
    sector_name: str,
    sector_score: float,
    fund_grade: str,
    fund_score: float,
    tech_label: str,
    tech_score: float,
    inst_signal: Optional[str] = None,
) -> str:
    inst_bit = f"、三大法人呈現「{inst_signal}」" if inst_signal else ""
    return (
        f"{name}隸屬「{sector_name}」（產業利多 {sector_score:.1f} 分），"
        f"基本面評級 {fund_grade}（{fund_score:.1f} 分）、技術面呈現「{tech_label}」（{tech_score:.1f} 分）"
        f"{inst_bit}，綜合評等為「{rating}」。"
    )


def _match_stock_news(symbol: str, name: str, sector_id: str, news_items: List[NewsItem]) -> List[Dict[str, object]]:
    """嚴格只回傳真正直接提及該公司的有效新聞；無直接新聞時回傳空清單，絕不硬塞同產業無關報導。"""
    matched: List[NewsItem] = []
    seen = set()
    for n in news_items:
        if not is_valid_stock_news(n, symbol, name=name):
            continue
        key = (n.title or "").strip().lower()[:48]
        if key in seen:
            continue
        seen.add(key)
        matched.append(n)
        if len(matched) >= 5:
            break
    return [
        {
            "title": n.title,
            "summary": n.summary,
            "full_content": n.full_content or n.summary,
            "source": n.source,
            "macro_region": n.macro_region,
            "lang": n.lang,
            "published_at": n.published_at,
            "event_type": n.event_type,
            "event_reason": n.event_reason,
            "is_official": n.is_official,
            "sentiment_label": n.sentiment_label,
            "sentiment_score": n.sentiment_score,
            "link": n.link,
        }
        for n in matched
    ]


class StockIntelPipeline:
    def __init__(self, store: Optional[ReportStore] = None) -> None:
        self.collector = MarketCollector()
        self.store = store or ReportStore()

    def run_full_analysis(self, save_to_db: bool = True) -> MarketReport:
        """執行完整全球分析管線：全球多語新聞 -> 三大法人 -> 總經多空 -> 產業排行 -> 個股四維診斷與策略回測。"""
        # 1. 蒐集並評分全球多語系財經新聞
        news_items, news_mode = collect_news()
        score_news_items(news_items)

        # 2. 蒐集全球大盤指數 + 信用市場利差代理 (HYG/LQD/IEF/BKLN/KRE) + 台股三大法人買賣超金額
        benchmarks = self.collector.collect_benchmarks()
        credit_proxies = self.collector.collect_credit_proxies()
        tw_inst_raw = self.collector.collect_tw_market_institutional()
        tw_inst_market = analyze_tw_market_institutional(tw_inst_raw)

        macro, theme_intensity = deduce_macro_outlook(news_items, benchmarks, tw_institutional=tw_inst_market)
        spread_stress, _ = compute_systemic_spread_stress(credit_proxies, benchmarks)

        # 3. 併發抓取所有產業代表股（2年日K + 財報 + 台股三大法人買賣超張數）
        all_symbols = [st["symbol"] for sec in SECTORS for st in sec["stocks"]]
        bundles = self.collector.collect_stocks_batch(all_symbols, max_workers=8)

        pre_analyzed: Dict[str, Dict[str, object]] = {}
        mom_by_sector: Dict[str, List[float]] = {sec["id"]: [] for sec in SECTORS}
        fund_by_sector: Dict[str, List[float]] = {sec["id"]: [] for sec in SECTORS}

        for sec in SECTORS:
            sid = sec["id"]
            for st in sec["stocks"]:
                sym = st["symbol"].upper()
                bundle = bundles.get(sym)
                if not bundle:
                    continue
                tech = analyze_technicals(bundle["chart"])
                fund = analyze_fundamentals(bundle["fundamentals"], tech.price, st["market"])
                inst = analyze_tw_stock_institutional(bundle.get("institutional_raw")) if st["market"] == "TW" else None
                backtest = run_stock_backtest(bundle["chart"], market=st["market"])

                pre_analyzed[sym] = {
                    "meta": st,
                    "sector": sec,
                    "bundle": bundle,
                    "tech": tech,
                    "fund": fund,
                    "inst": inst,
                    "backtest": backtest,
                }
                mom_by_sector[sid].append((tech.score - 50.0) * 2.0)
                fund_by_sector[sid].append(fund.score)

        # 4. 計算並排序利多與利空產業排行（並預先擷取關鍵消息面催化報導內文）
        sectors = rank_sectors(news_items, theme_intensity, mom_by_sector, fund_by_sector)
        enrich_sector_catalysts_content(sectors, max_fetch=12)
        bullish_sectors, bearish_sectors = split_sector_recommendations(sectors, top_n=4)
        sector_score_map = {s.sector_id: s.score for s in sectors}

        # 5. 若有設定 LLM API Key，進行深度策略推演增強
        macro = enhance_with_llm(macro, sectors, news_items)

        # 6. 組合完整個股報告（台股加入三大法人籌碼權重 15%，並同步計算 AI 信用風險五維雷達）
        stock_reports: List[StockReport] = []
        for sym, item in pre_analyzed.items():
            meta = item["meta"]
            sec = item["sector"]
            bundle = item["bundle"]
            tech = item["tech"]
            fund = item["fund"]
            inst = item["inst"]
            backtest = item["backtest"]
            sec_score = sector_score_map.get(sec["id"], 50.0)

            if inst is not None:
                total_score = round(
                    fund.score * 0.40 + tech.score * 0.30 + sec_score * 0.15 + inst.score * 0.15,
                    1,
                )
            else:
                total_score = round(fund.score * 0.45 + tech.score * 0.35 + sec_score * 0.20, 1)

            rating = _rate_stock(total_score, fund.score, tech.score)
            summary = _summarize_stock(
                meta["name"],
                rating,
                sec["name"],
                sec_score,
                fund.grade,
                fund.score,
                tech.trend_label,
                tech.score,
                inst_signal=inst.signal if inst else None,
            )
            rel_news = _match_stock_news(sym, meta["name"], sec["id"], news_items)
            credit_risk = analyze_stock_credit_risk(
                symbol=sym,
                name=meta["name"],
                sector_id=sec["id"],
                fundamentals=bundle["fundamentals"],
                chart=bundle["chart"],
                related_news=rel_news,
                systemic_spread_stress=spread_stress,
            )
            stock_reports.append(
                StockReport(
                    symbol=sym,
                    name=meta["name"],
                    market=meta["market"],
                    sector_id=sec["id"],
                    sector_name=sec["name"],
                    role=meta["role"],
                    total_score=total_score,
                    rating=rating,
                    summary=summary,
                    sector_score=sec_score,
                    fundamental=fund,
                    technical=tech,
                    institutional=inst,
                    backtest=backtest,
                    credit_risk=credit_risk,
                    related_news=rel_news,
                    data_mode="live",
                )
            )

        # 6.5 自動納入使用者「自選股」中尚未包含於預設 30 檔之自訂標的
        watchlist_entries = self.store.list_watchlist()
        analyzed_syms = {s.symbol.upper() for s in stock_reports}
        for w in watchlist_entries:
            wsym = str(w.get("symbol") or "").upper()
            if wsym and wsym not in analyzed_syms:
                extra = self.analyze_single_stock(wsym, sector_scores=sector_score_map, news_items=news_items)
                if extra:
                    stock_reports.append(extra)
                    analyzed_syms.add(extra.symbol.upper())

        stock_reports.sort(key=lambda s: s.total_score, reverse=True)

        # 7. 建構全球 × 個股 AI 信用風險雷達總報告
        credit_radar = build_credit_radar_report(
            news_items=news_items,
            benchmarks=benchmarks,
            credit_proxies=credit_proxies,
            stocks=stock_reports,
            enrich_articles=True,
        )

        data_mode = "live" if (news_mode == "live" and len(stock_reports) >= 12) else (
            "partial" if stock_reports else "fallback"
        )

        # 依高訊號程度、具體消息面事件與官方公告優先排序新聞
        ranked_news = sorted(
            news_items,
            key=lambda n: (
                abs(n.sentiment_score) * 2.0
                + (0.9 if n.event_type else 0.0)
                + (0.7 if n.is_official else 0.0)
                + len(n.matched_sectors) * 0.45
                + len(n.matched_themes) * 0.35
            ),
            reverse=True,
        )

        report = MarketReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            data_mode=data_mode,
            news_count=len(news_items),
            stocks_analyzed=len(stock_reports),
            macro=macro,
            sectors=sectors,
            bullish_sectors=bullish_sectors,
            bearish_sectors=bearish_sectors,
            stocks=stock_reports,
            news=ranked_news[:90],
            credit_radar=credit_radar,
            watchlist=watchlist_entries,
        )

        if save_to_db:
            self.store.save_report(report.to_dict())

        return report

    def analyze_single_stock(
        self,
        raw_symbol: str,
        sector_scores: Optional[Dict[str, float]] = None,
        news_items: Optional[List[NewsItem]] = None,
    ) -> Optional[StockReport]:
        """即時分析任意美股或台股代號（含基本面、技術面、三大法人買賣超與 2 年期策略回測）。"""
        bundle = self.collector.collect_stock_bundle(raw_symbol, range_str="2y")
        if not bundle:
            return None

        sym = bundle["symbol"].upper()
        market = bundle["market"]
        tech = analyze_technicals(bundle["chart"])
        fund = analyze_fundamentals(bundle["fundamentals"], tech.price, market)
        inst = analyze_tw_stock_institutional(bundle.get("institutional_raw")) if market == "TW" else None
        backtest = run_stock_backtest(bundle["chart"], market=market)

        known = STOCK_LOOKUP.get(sym)
        if known:
            name = known["name"]
            sector_id = known["sector_id"]
            sector_name = known["sector_name"]
            role = known["role"]
        else:
            name = str(bundle["fundamentals"].get("name") or bundle["chart"].get("short_name") or sym)
            sector_id = "custom"
            sector_name = str(
                bundle["fundamentals"].get("industry_raw")
                or bundle["fundamentals"].get("sector_raw")
                or ("台股上市櫃" if market == "TW" else "美股自選標的")
            )
            role = "使用者即時查詢標的"

        sec_score = (sector_scores or {}).get(sector_id, 55.0)
        if inst is not None:
            total_score = round(
                fund.score * 0.40 + tech.score * 0.30 + sec_score * 0.15 + inst.score * 0.15,
                1,
            )
        else:
            total_score = round(fund.score * 0.45 + tech.score * 0.35 + sec_score * 0.20, 1)

        rating = _rate_stock(total_score, fund.score, tech.score)
        summary = _summarize_stock(
            name,
            rating,
            sector_name,
            sec_score,
            fund.grade,
            fund.score,
            tech.trend_label,
            tech.score,
            inst_signal=inst.signal if inst else None,
        )
        pool_news = list(news_items or [])
        direct_existing = _match_stock_news(sym, name, sector_id, pool_news)
        if not direct_existing:
            stock_specific = collect_stock_news(sym, name=name, market=market, max_items=5)
            if stock_specific:
                score_news_items(stock_specific)
                pool_news = stock_specific + pool_news
        related = _match_stock_news(sym, name, sector_id, pool_news)
        credit_risk = analyze_stock_credit_risk(
            symbol=sym,
            name=name,
            sector_id=sector_id,
            fundamentals=bundle["fundamentals"],
            chart=bundle["chart"],
            related_news=related,
            systemic_spread_stress=42.0,
        )

        return StockReport(
            symbol=sym,
            name=name,
            market=market,
            sector_id=sector_id,
            sector_name=sector_name,
            role=role,
            total_score=total_score,
            rating=rating,
            summary=summary,
            sector_score=sec_score,
            fundamental=fund,
            technical=tech,
            institutional=inst,
            backtest=backtest,
            credit_risk=credit_risk,
            related_news=related,
            data_mode="live",
        )
