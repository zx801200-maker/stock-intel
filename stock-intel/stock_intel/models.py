"""核心資料模型（新增全球區域情緒、台股三大法人買賣超與量化策略回測模型）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NewsItem:
    id: str
    title: str
    summary: str
    link: str
    source: str
    region: str
    lang: str
    published_at: str
    macro_region: str = "北美"          # 北美 | 歐洲 | 日本 | 韓國 | 亞太新興 | 台灣 | 中東全球
    sentiment_score: float = 0.0        # -1.0 (極度利空) ~ +1.0 (極度利多)
    sentiment_label: str = "中性"        # 利多 | 偏多 | 中性 | 偏空 | 利空
    impact_weight: float = 1.0
    event_type: str = ""                # 合約/併購利多 | 官方核准/政策 | 監管調查/出口管制 | 經營層危機 ...
    event_reason: str = ""              # 具體消息面因果說明
    full_content: str = ""              # 完整報導內文或長摘要（供點入展開閱讀）
    is_official: bool = False           # 是否為證交所／官方重大訊息公告
    matched_sectors: List[str] = field(default_factory=list)
    matched_themes: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class BenchmarkQuote:
    symbol: str
    name: str
    category: str
    price: float
    change_pct_1d: float
    change_pct_5d: float
    change_pct_1m: float
    invert_sentiment: bool = False
    signal: str = "中性"


@dataclass
class RegionSentiment:
    region: str
    news_count: int
    avg_score: float                    # -100 ~ +100
    direction: str                      # 偏多 | 中性 | 偏空
    top_headline: str = ""


@dataclass
class TWMarketInstitutional:
    date: str                           # 如 2026-11-20
    foreign_net_billion: float          # 外資及陸資買賣超（億元）
    trust_net_billion: float            # 投信買賣超（億元）
    dealer_net_billion: float           # 自營商買賣超（億元）
    total_net_billion: float            # 三大法人合計（億元）
    signal: str                         # 法人大買 | 溫和買超 | 籌碼分歧 | 溫和賣超 | 法人大賣
    summary: str


@dataclass
class TWStockInstitutional:
    date: str
    foreign_net_lots: int               # 外資買賣超（張）
    trust_net_lots: int                 # 投信買賣超（張）
    dealer_net_lots: int                # 自營商買賣超（張）
    total_net_lots: int                 # 三大法人合計（張）
    score: float                        # 0 ~ 100 籌碼面評分
    signal: str                         # 土洋合擊買超 | 外資主導買超 | 投信認養 | 籌碼中性 | 法人調節賣超 | 土洋同步賣超
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)


@dataclass
class MacroThemeSignal:
    theme_id: str
    theme_name: str
    direction: str          # 利多 | 利空 | 中性
    score: float            # -100 ~ +100
    news_count: int
    reasoning: str


@dataclass
class MacroOutlook:
    overall_score: float                # -100 (強烈利空) ~ +100 (強烈利多)
    stance: str                         # 強烈利多 | 溫和利多 | 震盪中性 | 溫和利空 | 警戒利空
    confidence: int                     # 0 ~ 100
    news_sentiment_score: float         # -100 ~ +100
    market_momentum_score: float        # -100 ~ +100
    risk_index_score: float             # -100 ~ +100 (VIX / 殖利率壓力)
    executive_summary: str
    bullish_catalysts: List[str] = field(default_factory=list)
    bearish_risks: List[str] = field(default_factory=list)
    action_plan: List[str] = field(default_factory=list)
    themes: List[MacroThemeSignal] = field(default_factory=list)
    benchmarks: List[BenchmarkQuote] = field(default_factory=list)
    region_summary: List[RegionSentiment] = field(default_factory=list)
    tw_institutional: Optional[TWMarketInstitutional] = None
    analysis_engine: str = "local_quant"  # local_quant | gemini | openai
    llm_commentary: Optional[str] = None


@dataclass
class SectorOutlook:
    sector_id: str
    name: str
    en_name: str
    description: str
    score: float                        # 0 ~ 100 (綜合利多評分)
    outlook_label: str                  # 高度利多 | 溫和利多 | 中性觀察 | 偏空承壓
    news_score: float                   # -100 ~ +100
    macro_tailwind_score: float         # -100 ~ +100
    price_momentum_score: float         # -100 ~ +100
    news_count: int
    news_summary_reason: str = ""       # 一句白話總結：因何消息面事件利多或利空
    key_drivers: List[str] = field(default_factory=list)
    key_risks: List[str] = field(default_factory=list)
    bullish_catalysts_news: List[Dict[str, Any]] = field(default_factory=list)
    bearish_catalysts_news: List[Dict[str, Any]] = field(default_factory=list)
    top_headlines: List[Dict[str, Any]] = field(default_factory=list)
    stock_symbols: List[str] = field(default_factory=list)


@dataclass
class TechnicalAnalysis:
    score: float                        # 0 ~ 100
    trend_label: str                    # 強勢多頭 | 溫和偏多 | 區間震盪 | 弱勢偏空 | 空頭排列
    price: float
    change_pct_1d: float
    change_pct_5d: float
    change_pct_20d: float
    change_pct_60d: float
    ma5: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_mid: Optional[float] = None
    bb_lower: Optional[float] = None
    k_val: Optional[float] = None
    d_val: Optional[float] = None
    volume_ratio: Optional[float] = None
    atr_pct: Optional[float] = None
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    distance_52w_high_pct: Optional[float] = None
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    series: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FundamentalAnalysis:
    score: float                        # 0 ~ 100
    grade: str                          # A+ | A | B+ | B | C | D
    market_cap: Optional[float] = None
    currency: str = "USD"
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield_pct: Optional[float] = None
    roe_pct: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    operating_margin_pct: Optional[float] = None
    profit_margin_pct: Optional[float] = None
    revenue_growth_pct: Optional[float] = None
    earnings_growth_pct: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    free_cash_flow: Optional[float] = None
    target_mean_price: Optional[float] = None
    target_upside_pct: Optional[float] = None
    analyst_consensus: Optional[str] = None
    twse_monthly_rev_yoy_pct: Optional[float] = None
    twse_monthly_rev_mom_pct: Optional[float] = None
    twse_cum_rev_yoy_pct: Optional[float] = None
    twse_rev_period: Optional[str] = None
    data_source: str = "yahoo"
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)


@dataclass
class StockCreditRisk:
    risk_score: float                   # 0 (極低風險) ~ 100 (極高違約/信用壓力)
    credit_rating: str                  # AAA | AA | A | BBB | BB | B | CCC
    risk_level: str                     # 低風險 | 留意觀察 | 中度警戒 | 高危紅燈
    dimensions: Dict[str, float] = field(default_factory=dict)  # leverage, liquidity, cashflow, market_stress, event_risk
    metrics: Dict[str, Optional[float]] = field(default_factory=dict)
    red_flags: List[str] = field(default_factory=list)
    buffers: List[str] = field(default_factory=list)
    ai_diagnosis: str = ""


@dataclass
class CreditRadarReport:
    systemic_score: float               # 0 ~ 100 系統性信用風險總指數
    risk_level: str                     # 低風險 | 留意觀察 | 中度警戒 | 高危紅燈
    spread_regime: str                  # 信用利差穩定 | 利差溫和擴大 | 信用利差緊繃 | 系統性信用壓力
    dimensions: Dict[str, float] = field(default_factory=dict)
    dimension_labels: List[Dict[str, str]] = field(default_factory=list)
    proxies: List[Dict[str, Any]] = field(default_factory=list)
    ai_summary: str = ""
    key_warnings: List[str] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)
    credit_news: List[Dict[str, Any]] = field(default_factory=list)
    watchlist: List[Dict[str, Any]] = field(default_factory=list)
    rating_distribution: Dict[str, int] = field(default_factory=dict)


@dataclass
class StockReport:
    symbol: str
    name: str
    market: str                         # US | TW
    sector_id: str
    sector_name: str
    role: str
    total_score: float
    rating: str                         # 強力關注 | 偏多布局 | 逢低觀察 | 中性觀望 | 謹慎避開
    summary: str
    sector_score: float
    fundamental: FundamentalAnalysis
    technical: TechnicalAnalysis
    institutional: Optional[TWStockInstitutional] = None
    backtest: Optional[Dict[str, Any]] = None
    credit_risk: Optional[StockCreditRisk] = None
    related_news: List[Dict[str, Any]] = field(default_factory=list)
    data_mode: str = "live"


@dataclass
class MarketReport:
    generated_at: str
    data_mode: str                      # live | partial | fallback
    news_count: int
    stocks_analyzed: int
    macro: MacroOutlook
    sectors: List[SectorOutlook] = field(default_factory=list)
    bullish_sectors: List[SectorOutlook] = field(default_factory=list)  # 產業利多／抗跌推薦排行
    bearish_sectors: List[SectorOutlook] = field(default_factory=list)  # 產業利空警戒／避開排行
    stocks: List[StockReport] = field(default_factory=list)
    news: List[NewsItem] = field(default_factory=list)
    credit_radar: Optional[CreditRadarReport] = None
    watchlist: List[Dict[str, Any]] = field(default_factory=list)
    disclaimer: str = (
        "免責聲明：本系統所提供之全球新聞情緒推演、台股三大法人籌碼、量化策略回測、AI信用風險雷達、基本面與技術面分析均屬量化研究與資訊整理，"
        "不構成任何投資建議或買賣保證。過去回測績效不代表未來獲利，股市投資具波動風險，請審慎評估。"
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
