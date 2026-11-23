"""系統設定：全球多語系財經新聞來源（北美/歐洲/日本/韓國/亞太/中東/台灣）、大盤指標與美台供應鏈標的池。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, TypedDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "reports"
DB_PATH = DATA_DIR / "stock_intel.db"


def load_dotenv(env_path: Path | None = None) -> None:
    """輕量載入 .env 檔案，不依賴額外套件。"""
    target = env_path or (BASE_DIR / ".env")
    if not target.exists():
        return
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()

HTTP_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class FeedSource(TypedDict):
    id: str
    name: str
    region: str        # 細分地區標示
    macro_region: str  # 全球六大板塊歸類：北美 | 歐洲 | 日本 | 韓國 | 台灣 | 亞太新興 | 中東全球
    lang: str          # en | zh | ja | ko | de | fr
    url: str
    weight: float


# 全球跨語系免費財經新聞 RSS（覆蓋北美、歐洲英德法、日本、韓國、新加坡、印度、中東與台灣）
RSS_FEEDS: List[FeedSource] = [
    # ---- 北美 / 美國華爾街 ----
    {
        "id": "cnbc_top",
        "name": "CNBC Top News",
        "region": "美國/華爾街",
        "macro_region": "北美",
        "lang": "en",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        "weight": 1.3,
    },
    {
        "id": "cnbc_finance",
        "name": "CNBC Finance",
        "region": "美國/金融",
        "macro_region": "北美",
        "lang": "en",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "weight": 1.3,
    },
    {
        "id": "cnbc_tech",
        "name": "CNBC Tech",
        "region": "美國/科技",
        "macro_region": "北美",
        "lang": "en",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
        "weight": 1.25,
    },
    {
        "id": "marketwatch_pulse",
        "name": "MarketWatch MarketPulse",
        "region": "美國/盤中快訊",
        "macro_region": "北美",
        "lang": "en",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
        "weight": 1.25,
    },
    {
        "id": "gnews_us_biz",
        "name": "Google Business (US)",
        "region": "美國/綜合財經",
        "macro_region": "北美",
        "lang": "en",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en",
        "weight": 1.2,
    },
    # ---- 歐洲（英國 / 德國 / 法國 / 歐元區）----
    {
        "id": "bbc_business",
        "name": "BBC Business",
        "region": "英國/歐洲",
        "macro_region": "歐洲",
        "lang": "en",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "weight": 1.25,
    },
    {
        "id": "guardian_business",
        "name": "The Guardian Business",
        "region": "英國/歐洲",
        "macro_region": "歐洲",
        "lang": "en",
        "url": "https://www.theguardian.com/uk/business/rss",
        "weight": 1.15,
    },
    {
        "id": "gnews_uk_biz",
        "name": "Google Business (UK)",
        "region": "英國/倫敦",
        "macro_region": "歐洲",
        "lang": "en",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-GB&gl=GB&ceid=GB:en",
        "weight": 1.15,
    },
    {
        "id": "gnews_de_biz",
        "name": "Google Wirtschaft (DE)",
        "region": "德國/歐元區",
        "macro_region": "歐洲",
        "lang": "de",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=de&gl=DE&ceid=DE:de",
        "weight": 1.15,
    },
    {
        "id": "gnews_fr_biz",
        "name": "Google Économie (FR)",
        "region": "法國/歐元區",
        "macro_region": "歐洲",
        "lang": "fr",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=fr&gl=FR&ceid=FR:fr",
        "weight": 1.1,
    },
    # ---- 日本 / 東京市場 ----
    {
        "id": "gnews_jp_biz",
        "name": "Google ビジネス (日本)",
        "region": "日本/日股",
        "macro_region": "日本",
        "lang": "ja",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ja&gl=JP&ceid=JP:ja",
        "weight": 1.2,
    },
    # ---- 韓國 / 首爾半導體與出口 ----
    {
        "id": "gnews_kr_biz",
        "name": "Google 비즈니스 (韓國)",
        "region": "韓國/韓股",
        "macro_region": "韓國",
        "lang": "ko",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
        "weight": 1.2,
    },
    # ---- 亞太新興市場（新加坡 / 印度）----
    {
        "id": "gnews_sg_biz",
        "name": "Google Business (Singapore)",
        "region": "新加坡/東協",
        "macro_region": "亞太新興",
        "lang": "en",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-SG&gl=SG&ceid=SG:en",
        "weight": 1.15,
    },
    {
        "id": "gnews_in_biz",
        "name": "Google Business (India)",
        "region": "印度/南亞",
        "macro_region": "亞太新興",
        "lang": "en",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en",
        "weight": 1.1,
    },
    # ---- 中東與全球地緣政治 ----
    {
        "id": "cnbc_world",
        "name": "CNBC World Economy",
        "region": "全球總經",
        "macro_region": "中東全球",
        "lang": "en",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362",
        "weight": 1.2,
    },
    {
        "id": "aljazeera_world",
        "name": "Al Jazeera Global",
        "region": "中東/全球地緣",
        "macro_region": "中東全球",
        "lang": "en",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "weight": 1.05,
    },
    # ---- 台灣市場 ----
    {
        "id": "gnews_tw_biz",
        "name": "Google 財經新聞 (台灣)",
        "region": "台灣/財經",
        "macro_region": "台灣",
        "lang": "zh",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "weight": 1.3,
    },
    {
        "id": "gnews_tw_tech",
        "name": "Google 科技產業新聞 (台灣)",
        "region": "台灣/科技",
        "macro_region": "台灣",
        "lang": "zh",
        "url": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "weight": 1.15,
    },
    # ---- 企業合約／併購／官方公告／監管調查專屬催化源（限定權威財經媒體）----
    {
        "id": "gnews_us_catalysts",
        "name": "美股權威媒體企業事件/監管快訊",
        "region": "美國/企業事件",
        "macro_region": "北美",
        "lang": "en",
        "url": "https://news.google.com/rss/search?q=(contract+OR+deal+OR+acquisition+OR+FDA+OR+%22export+control%22+OR+%22SEC+probe%22)+(site:reuters.com+OR+site:bloomberg.com+OR+site:cnbc.com+OR+site:wsj.com+OR+site:ft.com+OR+site:marketwatch.com+OR+site:barrons.com+OR+site:apnews.com)+when:4d&hl=en-US&gl=US&ceid=US:en",
        "weight": 1.35,
    },
    {
        "id": "gnews_tw_catalysts",
        "name": "台股權威媒體合約/訂單/政策快訊",
        "region": "台灣/企業事件",
        "macro_region": "台灣",
        "lang": "zh",
        "url": "https://news.google.com/rss/search?q=(%E5%90%88%E7%B4%84+OR+%E5%A4%A7%E5%96%AE+OR+%E8%A8%82%E5%96%AE+OR+%E6%A0%B8%E5%87%86+OR+%E8%A3%81%E5%93%A1+OR+%E8%AA%BF%E6%9F%A5)+(site:money.udn.com+OR+site:ctee.com.tw+OR+site:cna.com.tw+OR+site:cnyes.com+OR+site:ec.ltn.com.tw+OR+site:moneydj.com+OR+site:digitimes.com.tw+OR+site:technews.tw)+when:4d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "weight": 1.35,
    },
    {
        "id": "gnews_credit_risk",
        "name": "全球權威媒體企業信用/債市違約快訊",
        "region": "全球/信用市場",
        "macro_region": "北美",
        "lang": "en",
        "url": "https://news.google.com/rss/search?q=(%22credit+spread%22+OR+%22high+yield%22+OR+%22private+credit%22+OR+%22credit+downgrade%22+OR+%22corporate+debt%22+OR+%22default+risk%22)+(site:reuters.com+OR+site:bloomberg.com+OR+site:wsj.com+OR+site:ft.com+OR+site:cnbc.com+OR+site:marketwatch.com+OR+site:barrons.com+OR+site:spglobal.com)+when:5d&hl=en-US&gl=US&ceid=US:en",
        "weight": 1.25,
    },
]

# 台灣證交所官方公告與上市公司重大訊息 OpenAPI
TWSE_MOPS_MATERIAL_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
TWSE_OFFICIAL_NEWS_URL = "https://openapi.twse.com.tw/v1/news/newsList"


class BenchmarkDef(TypedDict):
    symbol: str
    name: str
    category: str
    invert_sentiment: bool  # True 表示上漲對股市偏向利空（如 VIX、美債殖利率）


MACRO_BENCHMARKS: List[BenchmarkDef] = [
    {"symbol": "^GSPC", "name": "標普 500 (S&P 500)", "category": "美股大盤", "invert_sentiment": False},
    {"symbol": "^IXIC", "name": "那斯達克 (NASDAQ)", "category": "美股科技", "invert_sentiment": False},
    {"symbol": "^SOX", "name": "費城半導體 (SOX)", "category": "半導體指標", "invert_sentiment": False},
    {"symbol": "^TWII", "name": "台灣加權指數 (TAIEX)", "category": "台股大盤", "invert_sentiment": False},
    {"symbol": "^N225", "name": "日經 225 (Nikkei)", "category": "亞股/日本", "invert_sentiment": False},
    {"symbol": "^GDAXI", "name": "德國 DAX 指數", "category": "歐股指標", "invert_sentiment": False},
    {"symbol": "^VIX", "name": "恐慌指數 (VIX)", "category": "波動避險", "invert_sentiment": True},
    {"symbol": "^TNX", "name": "美國10年期公債殖利率", "category": "利率環境", "invert_sentiment": True},
    {"symbol": "GC=F", "name": "黃金期貨 (Gold)", "category": "避險資產", "invert_sentiment": False},
    {"symbol": "CL=F", "name": "WTI 原油", "category": "能源通膨", "invert_sentiment": False},
]

# AI 信用風險雷達：全球信用利差、槓桿貸款與銀行信用即時代理指標
CREDIT_PROXIES: List[BenchmarkDef] = [
    {"symbol": "HYG", "name": "美國高收益債 ETF (HYG)", "category": "高收益信用", "invert_sentiment": False},
    {"symbol": "LQD", "name": "美國投資級公司債 ETF (LQD)", "category": "投資級信用", "invert_sentiment": False},
    {"symbol": "IEF", "name": "美國7-10年公債 ETF (IEF)", "category": "無風險基準", "invert_sentiment": False},
    {"symbol": "BKLN", "name": "美國槓桿貸款 ETF (BKLN)", "category": "私募/槓桿信貸", "invert_sentiment": False},
    {"symbol": "KRE", "name": "美國區域銀行 ETF (KRE)", "category": "銀行體系信用", "invert_sentiment": False},
]


class StockMeta(TypedDict):
    symbol: str
    name: str
    market: str  # "US" | "TW"
    role: str


class SectorDef(TypedDict):
    id: str
    name: str
    en_name: str
    description: str
    keywords_en: List[str]
    keywords_zh: List[str]
    keywords_intl: List[str]  # 日/韓/德/法語系產業關鍵詞
    macro_sensitivity: Dict[str, float]
    stocks: List[StockMeta]


# 8 大跨市場核心產業與美台供應鏈對照（支援全球多語系新聞自動歸因）
SECTORS: List[SectorDef] = [
    {
        "id": "ai_semis",
        "name": "AI 與半導體晶片",
        "en_name": "AI & Semiconductors",
        "description": "涵蓋 GPU、AI 加速器、先進製程晶圓代工與封測，對全球 AI 資本支出與費半走勢高度敏感。",
        "keywords_en": [
            "nvidia", "tsmc", "semiconductor", "chip", "chips", "ai chip", "gpu", "foundry",
            "wafer", "broadcom", "amd", "asml", "blackwell", "hbm", "dram", "memory",
            "data center", "artificial intelligence", "export control", "chip tariff", "export permit",
        ],
        "keywords_zh": [
            "半導體", "台積電", "輝達", "晶片", "晶圓", "先進製程", "封測", "AI晶片",
            "聯發科", "記憶體", "HBM", "CoWoS", "算力", "費半", "出口管制",
        ],
        "keywords_intl": [
            "半導体", "エヌビディア", "チップ", "生成ai", "반도체", "엔비디아", "삼성전자", "하이닉스",
            "halbleiter", "ki-chip", "semi-conducteur", "puces",
        ],
        "macro_sensitivity": {"ai_capex": 1.6, "rate_cut": 0.9, "tariff_risk": -1.1, "recession": -0.8},
        "stocks": [
            {"symbol": "NVDA", "name": "NVIDIA 輝達", "market": "US", "role": "AI GPU 龍頭"},
            {"symbol": "AVGO", "name": "Broadcom 博通", "market": "US", "role": "客製化 AI ASIC 與網通"},
            {"symbol": "2330.TW", "name": "台積電", "market": "TW", "role": "全球先進製程晶圓代工龍頭"},
            {"symbol": "2454.TW", "name": "聯發科", "market": "TW", "role": "邊緣 AI 與手機旗艦晶片"},
        ],
    },
    {
        "id": "cloud_servers",
        "name": "雲端巨頭與 AI 伺服器",
        "en_name": "Cloud & AI Servers",
        "description": "雲端服務商（CSP）與台灣 ODM 伺服器代工鏈，受惠企業雲端轉型與 AI 基礎設施擴建。",
        "keywords_en": [
            "cloud", "aws", "azure", "google cloud", "microsoft", "alphabet", "amazon",
            "meta", "capex", "server", "hyperscaler", "rack", "liquid cooling", "foxconn",
            "software", "saas", "enterprise ai", "openai", "anthropic", "gemini",
        ],
        "keywords_zh": [
            "雲端", "伺服器", "AI伺服器", "鴻海", "廣達", "緯創", "微軟", "亞馬遜",
            "資本支出", "資料中心", "液冷", "代工", "機櫃", "CSP",
        ],
        "keywords_intl": [
            "クラウド", "データセンター", "サーバー", "클라우드", "데이터센터", "서버",
            "rechenzentrum", "intelligence artificielle", "serveur",
        ],
        "macro_sensitivity": {"ai_capex": 1.5, "rate_cut": 0.8, "tariff_risk": -0.7, "recession": -0.6},
        "stocks": [
            {"symbol": "MSFT", "name": "Microsoft 微軟", "market": "US", "role": "企業雲端與 AI 軟體龍頭"},
            {"symbol": "AMZN", "name": "Amazon 亞馬遜", "market": "US", "role": "AWS 雲端與電商龍頭"},
            {"symbol": "2317.TW", "name": "鴻海", "market": "TW", "role": "AI 伺服器組裝與電動車代工"},
            {"symbol": "2382.TW", "name": "廣達", "market": "TW", "role": "雲端與 AI 伺服器主力 ODM"},
        ],
    },
    {
        "id": "power_energy",
        "name": "重電、電力網與能源",
        "en_name": "Power Grid & Energy",
        "description": "AI 資料中心耗電激增帶動電網升級、電源管理與儲能需求，兼具能源通膨避險屬性。",
        "keywords_en": [
            "power", "grid", "electricity", "nuclear", "energy", "oil", "crude", "opec",
            "utility", "solar", "renewable", "battery", "transformer", "natural gas",
            "data center power", "exxon", "chevron", "ge vernova", "saudi",
        ],
        "keywords_zh": [
            "重電", "電力", "電網", "儲能", "能源", "台達電", "華城", "變壓器",
            "核電", "綠能", "原油", "油價", "缺電", "電源", "發電",
        ],
        "keywords_intl": [
            "電力", "原発", "エネルギー", "原油", "전력", "에너지", "원전", "유가",
            "energie", "strom", "ölpreis", "nucléaire", "pétrole",
        ],
        "macro_sensitivity": {"ai_capex": 1.1, "inflation_oil": 1.2, "rate_cut": 0.6, "geopolitics": 0.9},
        "stocks": [
            {"symbol": "NEE", "name": "NextEra Energy", "market": "US", "role": "北美再生能源與公用電力龍頭"},
            {"symbol": "XOM", "name": "Exxon Mobil 艾克森美孚", "market": "US", "role": "全球綜合能源巨頭"},
            {"symbol": "2308.TW", "name": "台達電", "market": "TW", "role": "AI 伺服器電源與液冷散熱龍頭"},
            {"symbol": "1519.TW", "name": "華城", "market": "TW", "role": "北美電網升級高壓變壓器主力"},
        ],
    },
    {
        "id": "financials",
        "name": "金融銀行與金控",
        "en_name": "Financials & Banking",
        "description": "受惠殖利率曲線陡峭化、投資銀行併購回溫與壽險資本利得，為穩健高股息配置核心。",
        "keywords_en": [
            "bank", "banks", "jpmorgan", "goldman", "morgan stanley", "fed", "federal reserve",
            "ecb", "boe", "boj", "interest rate", "yield", "treasury", "credit", "lending",
            "fintech", "insurance", "ipo", "m&a", "wall street", "net interest",
        ],
        "keywords_zh": [
            "金融", "銀行", "金控", "壽險", "富邦金", "國泰金", "升息", "降息",
            "殖利率", "美債", "聯準會", "央行", "放款", "股利", "高股息",
        ],
        "keywords_intl": [
            "日銀", "銀行", "金利", "為替", "円安", "円高", "금리", "은행", "금융", "한국은행",
            "ezb", "zinsen", "bank", "banque", "taux d'intérêt",
        ],
        "macro_sensitivity": {"rate_cut": 0.4, "soft_landing": 1.2, "recession": -1.3, "inflation_oil": 0.3},
        "stocks": [
            {"symbol": "JPM", "name": "JPMorgan Chase 摩根大通", "market": "US", "role": "美國資產規模最大綜合銀行"},
            {"symbol": "GS", "name": "Goldman Sachs 高盛", "market": "US", "role": "投資銀行與資本市場龍頭"},
            {"symbol": "2881.TW", "name": "富邦金", "market": "TW", "role": "台灣壽險與銀行金控獲利王"},
            {"symbol": "2882.TW", "name": "國泰金", "market": "TW", "role": "台灣最大資產規模壽險金控"},
        ],
    },
    {
        "id": "consumer_ev",
        "name": "消費電子與電動車",
        "en_name": "Consumer Tech & EV",
        "description": "受消費力、AI 手機/PC 換機潮與電動車/自駕技術推進影響，對關稅與消費信心敏感。",
        "keywords_en": [
            "apple", "iphone", "tesla", "ev", "electric vehicle", "autonomous", "robotaxi",
            "consumer", "retail", "smartphone", "pc", "sales", "delivery", "automaker", "byd",
        ],
        "keywords_zh": [
            "蘋果", "iPhone", "特斯拉", "電動車", "自駕", "消費", "零售", "手機",
            "大立光", "換機潮", "銷量", "車用", "消費電子",
        ],
        "keywords_intl": [
            "自動車", "電気自動車", "トヨタ", "スマホ", "전기차", "현대차", "스마트폰",
            "elektroauto", "autoindustrie", "volkswagen", "voiture électrique",
        ],
        "macro_sensitivity": {"rate_cut": 1.1, "soft_landing": 1.0, "tariff_risk": -1.2, "recession": -1.0},
        "stocks": [
            {"symbol": "AAPL", "name": "Apple 蘋果", "market": "US", "role": "全球消費電子生態系龍頭"},
            {"symbol": "TSLA", "name": "Tesla 特斯拉", "market": "US", "role": "電動車、儲能與自駕機器人龍頭"},
            {"symbol": "3008.TW", "name": "大立光", "market": "TW", "role": "高階手機光學鏡頭全球龍頭"},
            {"symbol": "2301.TW", "name": "光寶科", "market": "TW", "role": "雲端電源與車用光電元件"},
        ],
    },
    {
        "id": "shipping_trade",
        "name": "航運與國際物流",
        "en_name": "Shipping & Global Trade",
        "description": "高度反映全球進出口貿易量、運價指數（SCFI）與地緣航道繞行變化。",
        "keywords_en": [
            "shipping", "freight", "container", "port", "supply chain", "logistics", "red sea",
            "suez", "panama canal", "trade", "export", "import", "ups", "fedex", "maersk",
        ],
        "keywords_zh": [
            "航運", "貨櫃", "運價", "SCFI", "長榮", "陽明", "紅海", "貿易",
            "關稅", "出口", "物流", "搶運", "海運", "空運",
        ],
        "keywords_intl": [
            "海運", "輸出", "輸入", "物流", "貿易", "수출", "무역", "해운", "물류",
            "exporte", "handel", "logistik", "commerce", "fret",
        ],
        "macro_sensitivity": {"geopolitics": 1.0, "soft_landing": 0.9, "tariff_risk": -0.6, "recession": -1.2},
        "stocks": [
            {"symbol": "FDX", "name": "FedEx 聯邦快遞", "market": "US", "role": "全球航空貨運與快遞指標"},
            {"symbol": "2603.TW", "name": "長榮", "market": "TW", "role": "全球前十大貨櫃航運高息指標"},
            {"symbol": "2609.TW", "name": "陽明", "market": "TW", "role": "台灣遠洋貨櫃航運主要業者"},
        ],
    },
    {
        "id": "healthcare_bio",
        "name": "醫療保健與生技製藥",
        "en_name": "Healthcare & Biotech",
        "description": "景氣防禦型剛性需求，並受惠 GLP-1 減重藥、新藥 FDA 核准與高齡化趨勢。",
        "keywords_en": [
            "pharma", "biotech", "fda", "drugmaker", "prescription drug", "clinical trial",
            "healthcare", "obesity", "glp-1", "eli lilly", "novo nordisk", "vaccine",
            "medical device", "medicare", "oncology", "bayer", "astrazeneca",
        ],
        "keywords_zh": [
            "生技", "製藥", "新藥", "FDA", "醫療", "臨床", "藥華藥", "美時",
            "減重藥", "健保", "醫材", "防禦型",
        ],
        "keywords_intl": [
            "製薬", "バイオ", "新薬", "제약", "바이오", "신약",
            "pharma", "bayer", "sanofi", "médicament", "santé",
        ],
        "macro_sensitivity": {"recession": 0.8, "rate_cut": 0.7, "geopolitics": 0.3, "tariff_risk": -0.2},
        "stocks": [
            {"symbol": "LLY", "name": "Eli Lilly 禮來", "market": "US", "role": "全球減重與代謝新藥龍頭"},
            {"symbol": "UNH", "name": "UnitedHealth 聯合健康", "market": "US", "role": "美國醫療保險與照護龍頭"},
            {"symbol": "6446.TW", "name": "藥華藥", "market": "TW", "role": "台灣罕病新藥國際化指標"},
            {"symbol": "1795.TW", "name": "美時", "market": "TW", "role": "特殊學名藥與癌症用藥出口商"},
        ],
    },
    {
        "id": "defense_aero",
        "name": "航太軍工與國防安全",
        "en_name": "Defense & Aerospace",
        "description": "各國國防預算擴張、地緣衝突升溫與無人機／低軌衛星趨勢下的長線受惠族群。",
        "keywords_en": [
            "defense", "defence", "military", "pentagon", "nato", "drone", "aerospace", "missile",
            "war", "conflict", "geopolitical", "lockheed", "rtx", "boeing", "rheinmetall", "airbus",
        ],
        "keywords_zh": [
            "軍工", "國防", "航太", "無人機", "漢翔", "地緣政治", "衝突", "預算",
            "衛星", "安全", "軍購", "飛彈",
        ],
        "keywords_intl": [
            "防衛", "軍事", "ミサイル", "ドローン", "방산", "국방", "무기", "미사일",
            "rüstung", "verteidigung", "bundeswehr", "défense", "armement",
        ],
        "macro_sensitivity": {"geopolitics": 1.6, "tariff_risk": 0.3, "recession": 0.5},
        "stocks": [
            {"symbol": "LMT", "name": "Lockheed Martin 洛克希德馬丁", "market": "US", "role": "全球國防航太系統龍頭"},
            {"symbol": "RTX", "name": "RTX Corp", "market": "US", "role": "防空飛彈與航太發動機大廠"},
            {"symbol": "2634.TW", "name": "漢翔", "market": "TW", "role": "台灣航太製造與國機國造龍頭"},
        ],
    },
]

# 快速查詢表：由股票代號反查所屬產業與預設名稱
STOCK_LOOKUP: Dict[str, Dict[str, str]] = {}
for _sec in SECTORS:
    for _st in _sec["stocks"]:
        STOCK_LOOKUP[_st["symbol"].upper()] = {
            "symbol": _st["symbol"].upper(),
            "name": _st["name"],
            "market": _st["market"],
            "role": _st["role"],
            "sector_id": _sec["id"],
            "sector_name": _sec["name"],
        }
