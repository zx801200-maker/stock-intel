"""美股與台股即時行情、2年歷史K線、基本面與台股三大法人買賣超蒐集器（Yahoo Finance + TWSE）。"""

from __future__ import annotations

import http.cookiejar
import json
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from stock_intel.config import CREDIT_PROXIES, HTTP_USER_AGENT, MACRO_BENCHMARKS
from stock_intel.models import BenchmarkQuote


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "" or val == "-":
        return None
    if isinstance(val, dict):
        val = val.get("raw")
    try:
        f = float(str(val).replace(",", "").strip())
        if f != f:
            return None
        return f
    except Exception:
        return None


def _safe_int(val: Any) -> int:
    f = _safe_float(val)
    return int(round(f)) if f is not None else 0


class YahooSession:
    """線程安全的 Yahoo Finance Cookie + Crumb 會話管理器（零外部依賴）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cj))
        self._opener.addheaders = [
            ("User-Agent", HTTP_USER_AGENT),
            ("Accept", "application/json, text/plain, */*"),
        ]
        self._crumb: Optional[str] = None
        self._initialized = False

    def ensure_crumb(self) -> Optional[str]:
        with self._lock:
            if self._initialized:
                return self._crumb
            self._initialized = True
            try:
                try:
                    self._opener.open("https://fc.yahoo.com", timeout=6)
                except Exception:
                    pass
                with self._opener.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=6) as r:
                    crumb = r.read().decode("utf-8", errors="ignore").strip()
                    if crumb and "<" not in crumb:
                        self._crumb = crumb
            except Exception:
                self._crumb = None
            return self._crumb

    def fetch_json(self, url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
        try:
            with self._opener.open(url, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception:
            return None

    def fetch_chart(self, symbol: str, range_str: str = "2y", interval: str = "1d") -> Optional[Dict[str, Any]]:
        encoded = urllib.parse.quote(symbol)
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
            f"?range={range_str}&interval={interval}&includePrePost=false"
        )
        data = self.fetch_json(url, timeout=10)
        if not data:
            return None
        results = (data.get("chart") or {}).get("result") or []
        if not results:
            return None
        res = results[0]
        meta = res.get("meta") or {}
        timestamps = res.get("timestamp") or []
        quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        bars: List[Dict[str, Any]] = []
        for idx, ts in enumerate(timestamps):
            c = _safe_float(closes[idx] if idx < len(closes) else None)
            if c is None or c <= 0:
                continue
            o = _safe_float(opens[idx] if idx < len(opens) else None) or c
            h = _safe_float(highs[idx] if idx < len(highs) else None) or max(o, c)
            l = _safe_float(lows[idx] if idx < len(lows) else None) or min(o, c)
            v = _safe_float(volumes[idx] if idx < len(volumes) else None) or 0.0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            bars.append(
                {
                    "date": dt,
                    "open": round(o, 4),
                    "high": round(h, 4),
                    "low": round(l, 4),
                    "close": round(c, 4),
                    "volume": int(v),
                }
            )
        if not bars:
            return None
        return {
            "symbol": meta.get("symbol", symbol),
            "short_name": meta.get("shortName") or meta.get("longName") or symbol,
            "currency": meta.get("currency", "USD"),
            "regular_price": _safe_float(meta.get("regularMarketPrice")) or bars[-1]["close"],
            "fifty_two_week_high": _safe_float(meta.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": _safe_float(meta.get("fiftyTwoWeekLow")),
            "bars": bars,
        }

    def fetch_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        crumb = self.ensure_crumb()
        if not crumb:
            return None
        encoded = urllib.parse.quote(symbol)
        modules = "financialData,defaultKeyStatistics,summaryDetail,assetProfile,price"
        url = (
            f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{encoded}"
            f"?modules={modules}&crumb={urllib.parse.quote(crumb)}"
        )
        data = self.fetch_json(url, timeout=10)
        if not data:
            return None
        results = (data.get("quoteSummary") or {}).get("result") or []
        if not results:
            return None
        res = results[0]
        fd = res.get("financialData") or {}
        sd = res.get("summaryDetail") or {}
        ks = res.get("defaultKeyStatistics") or {}
        ap = res.get("assetProfile") or {}
        pr = res.get("price") or {}

        div_yield = _safe_float(sd.get("dividendYield"))
        if div_yield is not None and div_yield < 1.0:
            div_yield = div_yield * 100.0

        def _pct(v: Any) -> Optional[float]:
            f = _safe_float(v)
            return round(f * 100.0, 2) if f is not None else None

        return {
            "name": pr.get("shortName") or pr.get("longName") or symbol,
            "currency": pr.get("currency") or sd.get("currency") or "USD",
            "sector_raw": ap.get("sector"),
            "industry_raw": ap.get("industry"),
            "market_cap": _safe_float(sd.get("marketCap") or pr.get("marketCap")),
            "pe_ratio": _safe_float(sd.get("trailingPE")),
            "forward_pe": _safe_float(sd.get("forwardPE") or ks.get("forwardPE")),
            "pb_ratio": _safe_float(ks.get("priceToBook")),
            "dividend_yield_pct": round(div_yield, 2) if div_yield is not None else None,
            "roe_pct": _pct(fd.get("returnOnEquity")),
            "gross_margin_pct": _pct(fd.get("grossMargins")),
            "operating_margin_pct": _pct(fd.get("operatingMargins")),
            "profit_margin_pct": _pct(fd.get("profitMargins")),
            "revenue_growth_pct": _pct(fd.get("revenueGrowth")),
            "earnings_growth_pct": _pct(fd.get("earningsGrowth") or ks.get("earningsQuarterlyGrowth")),
            "debt_to_equity": _safe_float(fd.get("debtToEquity")),
            "current_ratio": _safe_float(fd.get("currentRatio")),
            "quick_ratio": _safe_float(fd.get("quickRatio")),
            "total_cash": _safe_float(fd.get("totalCash")),
            "total_debt": _safe_float(fd.get("totalDebt")),
            "operating_cash_flow": _safe_float(fd.get("operatingCashflow")),
            "ebitda": _safe_float(fd.get("ebitda")),
            "total_revenue": _safe_float(fd.get("totalRevenue")),
            "beta": _safe_float(ks.get("beta") or sd.get("beta")),
            "free_cash_flow": _safe_float(fd.get("freeCashflow")),
            "target_mean_price": _safe_float(fd.get("targetMeanPrice")),
            "analyst_consensus": fd.get("recommendationKey"),
            "data_source": "yahoo",
        }


class TWSEOpenAPIClient:
    """
    台灣證券交易所官方資料整合：
    1. OpenAPI BWIBBU_ALL (PE/PB/殖利率) & t187ap05_L (最新月營收)
    2. RWD BFI82U (大盤三大法人買賣超金額)
    3. RWD T86 (全體上市個股三大法人買賣超張數)
    """

    BWIBBU_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    MONTHLY_REV_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
    BFI82U_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json"
    T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALLBUT0999"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._inst_loaded = False
        self._valuation_map: Dict[str, Dict[str, Any]] = {}
        self._revenue_map: Dict[str, Dict[str, Any]] = {}
        self._market_inst: Optional[Dict[str, Any]] = None
        self._stock_inst_map: Dict[str, Dict[str, Any]] = {}

    def _fetch_json(self, url: str, timeout: int = 10) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))

    @staticmethod
    def _fmt_twse_date(raw_date: str) -> str:
        s = str(raw_date or "").strip()
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            try:
                rows = self._fetch_json(self.BWIBBU_URL)
                for row in rows:
                    code = str(row.get("Code", "")).strip()
                    if code:
                        self._valuation_map[code] = {
                            "name": row.get("Name", ""),
                            "pe_ratio": _safe_float(row.get("PEratio")),
                            "pb_ratio": _safe_float(row.get("PBratio")),
                            "dividend_yield_pct": _safe_float(row.get("DividendYield")),
                        }
            except Exception:
                pass
            try:
                rows = self._fetch_json(self.MONTHLY_REV_URL)
                for row in rows:
                    code = str(row.get("公司代號", "")).strip()
                    if code:
                        self._revenue_map[code] = {
                            "name": row.get("公司名稱", ""),
                            "industry": row.get("產業別", ""),
                            "period": row.get("資料年月", ""),
                            "monthly_rev_mom_pct": _safe_float(row.get("營業收入-上月比較增減(%)")),
                            "monthly_rev_yoy_pct": _safe_float(row.get("營業收入-去年同月增減(%)")),
                            "cum_rev_yoy_pct": _safe_float(row.get("累計營業收入-前期比較增減(%)")),
                        }
            except Exception:
                pass

    def _fetch_with_day_fallback(self, base_url: str) -> Optional[Dict[str, Any]]:
        """優先抓取最新交易日；若遇盤前尚未更新則自動往前回溯至最近有資料的交易日。"""
        try:
            d = self._fetch_json(base_url, timeout=10)
            if isinstance(d, dict) and d.get("stat") == "OK" and d.get("data"):
                return d
        except Exception:
            pass
        now_utc = datetime.now(timezone.utc) + timedelta(hours=8)
        for back in range(1, 6):
            dt_str = (now_utc - timedelta(days=back)).strftime("%Y%m%d")
            sep = "&" if "?" in base_url else "?"
            try:
                d = self._fetch_json(f"{base_url}{sep}date={dt_str}", timeout=10)
                if isinstance(d, dict) and d.get("stat") == "OK" and d.get("data"):
                    return d
            except Exception:
                continue
        return None

    def load_institutional(self) -> None:
        with self._lock:
            if self._inst_loaded:
                return
            self._inst_loaded = True

            # 1. 大盤三大法人買賣金額 (BFI82U)
            try:
                d = self._fetch_with_day_fallback(self.BFI82U_URL)
                if d and d.get("data"):
                    foreign_amt = 0.0
                    trust_amt = 0.0
                    dealer_amt = 0.0
                    total_amt = 0.0
                    for row in d["data"]:
                        label = str(row[0]).strip()
                        diff = _safe_float(row[3]) or 0.0
                        if "外資" in label:
                            foreign_amt += diff
                        elif "投信" in label:
                            trust_amt += diff
                        elif "自營商" in label:
                            dealer_amt += diff
                        elif "合計" in label:
                            total_amt = diff
                    if total_amt == 0.0:
                        total_amt = foreign_amt + trust_amt + dealer_amt
                    self._market_inst = {
                        "date": self._fmt_twse_date(d.get("date", "")),
                        "foreign_net_billion": round(foreign_amt / 1e8, 2),
                        "trust_net_billion": round(trust_amt / 1e8, 2),
                        "dealer_net_billion": round(dealer_amt / 1e8, 2),
                        "total_net_billion": round(total_amt / 1e8, 2),
                    }
            except Exception:
                self._market_inst = None

            # 2. 全體上市個股三大法人買賣超 (T86)
            try:
                d = self._fetch_with_day_fallback(self.T86_URL)
                if d and d.get("data"):
                    dt_str = self._fmt_twse_date(d.get("date", ""))
                    for row in d["data"]:
                        if len(row) < 19:
                            continue
                        code = str(row[0]).strip()
                        f_shares = _safe_int(row[4]) + _safe_int(row[7])
                        t_shares = _safe_int(row[10])
                        d_shares = _safe_int(row[11])
                        tot_shares = _safe_int(row[18])
                        self._stock_inst_map[code] = {
                            "date": dt_str,
                            "foreign_net_lots": int(round(f_shares / 1000.0)),
                            "trust_net_lots": int(round(t_shares / 1000.0)),
                            "dealer_net_lots": int(round(d_shares / 1000.0)),
                            "total_net_lots": int(round(tot_shares / 1000.0)),
                        }
            except Exception:
                pass

    def get_market_institutional(self) -> Optional[Dict[str, Any]]:
        self.load_institutional()
        return self._market_inst

    def get_stock_institutional(self, symbol: str) -> Optional[Dict[str, Any]]:
        self.load_institutional()
        code = symbol.upper().replace(".TW", "").replace(".TWO", "").strip()
        return self._stock_inst_map.get(code)

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        self.load()
        code = symbol.upper().replace(".TW", "").replace(".TWO", "").strip()
        val = self._valuation_map.get(code, {})
        rev = self._revenue_map.get(code, {})
        merged: Dict[str, Any] = {}
        merged.update(val)
        if rev:
            merged["twse_monthly_rev_mom_pct"] = (
                round(rev["monthly_rev_mom_pct"], 2) if rev.get("monthly_rev_mom_pct") is not None else None
            )
            merged["twse_monthly_rev_yoy_pct"] = (
                round(rev["monthly_rev_yoy_pct"], 2) if rev.get("monthly_rev_yoy_pct") is not None else None
            )
            merged["twse_cum_rev_yoy_pct"] = (
                round(rev["cum_rev_yoy_pct"], 2) if rev.get("cum_rev_yoy_pct") is not None else None
            )
            merged["twse_rev_period"] = rev.get("period")
            if rev.get("name") and not merged.get("name"):
                merged["name"] = rev["name"]
        return merged


class MarketCollector:
    """整合美股與台股大盤、2年日K線、基本面與台股三大法人籌碼的統一資料層。"""

    def __init__(self) -> None:
        self.yahoo = YahooSession()
        self.twse = TWSEOpenAPIClient()

    @staticmethod
    def normalize_symbol(raw: str) -> Tuple[str, str]:
        sym = raw.strip().upper()
        if sym.endswith(".TW") or sym.endswith(".TWO"):
            return sym, "TW"
        if sym.isdigit() and 4 <= len(sym) <= 6:
            return f"{sym}.TW", "TW"
        return sym, "US"

    def collect_tw_market_institutional(self) -> Optional[Dict[str, Any]]:
        return self.twse.get_market_institutional()

    def collect_benchmarks(self) -> List[BenchmarkQuote]:
        quotes: List[BenchmarkQuote] = []

        def _fetch_one(b: Dict[str, Any]) -> Optional[BenchmarkQuote]:
            chart = self.yahoo.fetch_chart(b["symbol"], range_str="2mo", interval="1d")
            if not chart or len(chart["bars"]) < 2:
                return None
            bars = chart["bars"]
            last = bars[-1]["close"]
            prev_1d = bars[-2]["close"]
            prev_5d = bars[-6]["close"] if len(bars) >= 6 else bars[0]["close"]
            prev_1m = bars[-22]["close"] if len(bars) >= 22 else bars[0]["close"]

            c1 = round((last - prev_1d) / prev_1d * 100.0, 2) if prev_1d else 0.0
            c5 = round((last - prev_5d) / prev_5d * 100.0, 2) if prev_5d else 0.0
            c1m = round((last - prev_1m) / prev_1m * 100.0, 2) if prev_1m else 0.0

            eff_5d = -c5 if b["invert_sentiment"] else c5
            if eff_5d >= 1.5:
                signal = "偏多支撐"
            elif eff_5d <= -1.5:
                signal = "偏空承壓"
            else:
                signal = "區間震盪"

            return BenchmarkQuote(
                symbol=b["symbol"],
                name=b["name"],
                category=b["category"],
                price=round(last, 2),
                change_pct_1d=c1,
                change_pct_5d=c5,
                change_pct_1m=c1m,
                invert_sentiment=b["invert_sentiment"],
                signal=signal,
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(_fetch_one, b) for b in MACRO_BENCHMARKS]
            for b, fut in zip(MACRO_BENCHMARKS, futs):
                try:
                    q = fut.result()
                    if q:
                        quotes.append(q)
                except Exception:
                    continue
        return quotes

    def collect_credit_proxies(self) -> List[Dict[str, Any]]:
        """併發抓取全球信用利差與銀行／槓桿信貸代理 ETF（HYG/LQD/IEF/BKLN/KRE）。"""
        proxies: List[Dict[str, Any]] = []

        def _fetch_proxy(b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            chart = self.yahoo.fetch_chart(b["symbol"], range_str="2mo", interval="1d")
            if not chart or len(chart["bars"]) < 2:
                return None
            bars = chart["bars"]
            last = bars[-1]["close"]
            prev_1d = bars[-2]["close"]
            prev_5d = bars[-6]["close"] if len(bars) >= 6 else bars[0]["close"]
            prev_1m = bars[-22]["close"] if len(bars) >= 22 else bars[0]["close"]
            return {
                "symbol": b["symbol"],
                "name": b["name"],
                "category": b["category"],
                "price": round(last, 2),
                "change_pct_1d": round((last - prev_1d) / prev_1d * 100.0, 2) if prev_1d else 0.0,
                "change_pct_5d": round((last - prev_5d) / prev_5d * 100.0, 2) if prev_5d else 0.0,
                "change_pct_1m": round((last - prev_1m) / prev_1m * 100.0, 2) if prev_1m else 0.0,
            }

        with ThreadPoolExecutor(max_workers=5) as pool:
            futs = [pool.submit(_fetch_proxy, b) for b in CREDIT_PROXIES]
            for fut in futs:
                try:
                    item = fut.result()
                    if item:
                        proxies.append(item)
                except Exception:
                    continue
        return proxies

    def collect_stock_bundle(self, symbol: str, range_str: str = "2y") -> Optional[Dict[str, Any]]:
        """單一股票抓取完整 2 年日線（供技術分析與策略回測）+ 基本面 + 台股三大法人籌碼。"""
        norm_sym, market = self.normalize_symbol(symbol)
        chart = self.yahoo.fetch_chart(norm_sym, range_str=range_str, interval="1d")
        if not chart and market == "TW" and norm_sym.endswith(".TW"):
            alt_sym = norm_sym.replace(".TW", ".TWO")
            chart = self.yahoo.fetch_chart(alt_sym, range_str=range_str, interval="1d")
            if chart:
                norm_sym = alt_sym

        if not chart:
            return None

        fundamentals = self.yahoo.fetch_fundamentals(norm_sym) or {"currency": chart.get("currency", "USD")}
        inst_raw: Optional[Dict[str, Any]] = None
        if market == "TW":
            twse_info = self.twse.get_stock_info(norm_sym)
            if twse_info:
                for key in ("pe_ratio", "pb_ratio", "dividend_yield_pct"):
                    if twse_info.get(key) is not None:
                        fundamentals[key] = twse_info[key]
                for key in (
                    "twse_monthly_rev_mom_pct",
                    "twse_monthly_rev_yoy_pct",
                    "twse_cum_rev_yoy_pct",
                    "twse_rev_period",
                ):
                    if twse_info.get(key) is not None:
                        fundamentals[key] = twse_info[key]
                fundamentals["data_source"] = "yahoo+twse"
            inst_raw = self.twse.get_stock_institutional(norm_sym)

        return {
            "symbol": norm_sym,
            "market": market,
            "chart": chart,
            "fundamentals": fundamentals,
            "institutional_raw": inst_raw,
        }

    def collect_stocks_batch(self, symbols: List[str], max_workers: int = 8) -> Dict[str, Dict[str, Any]]:
        """併發批次抓取多檔股票資料，預先暖機 Yahoo crumb、TWSE OpenAPI 與三大法人資料。"""
        self.yahoo.ensure_crumb()
        if any(s.upper().endswith(".TW") or s.upper().endswith(".TWO") for s in symbols):
            self.twse.load()
            self.twse.load_institutional()

        results: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {pool.submit(self.collect_stock_bundle, sym): sym for sym in symbols}
            for fut in as_completed(futs):
                orig = futs[fut]
                try:
                    bundle = fut.result()
                    if bundle:
                        results[orig.upper()] = bundle
                except Exception:
                    continue
        return results
