"""全球多語系財經新聞 RSS 併發蒐集器（覆蓋北美、歐洲、日本、韓國、東南亞、印度、中東與台灣）。"""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Tuple

from stock_intel.config import (
    HTTP_USER_AGENT,
    RSS_FEEDS,
    TWSE_MOPS_MATERIAL_URL,
    TWSE_OFFICIAL_NEWS_URL,
    FeedSource,
)
from stock_intel.models import NewsItem

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    unescaped = html.unescape(text)
    stripped = _TAG_RE.sub(" ", unescaped)
    return _WS_RE.sub(" ", stripped).strip()


def _parse_pub_date(raw: str | None) -> str:
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


from urllib.parse import urlparse

# =============================================================================
# 具公信力之國際與台灣權威財經媒體白名單（嚴格阻擋內容農場、散戶論壇、部落格與雜訊）
# =============================================================================
CREDIBLE_MEDIA_DOMAINS = (
    # 北美／全球一線通訊社與財經媒體
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "cnbc.com",
    "barrons.com",
    "marketwatch.com",
    "apnews.com",
    "afp.com",
    "nytimes.com",
    "washingtonpost.com",
    "economist.com",
    "fortune.com",
    "investors.com",
    "morningstar.com",
    "spglobal.com",
    "moodys.com",
    "fitchratings.com",
    "abcnews.com",
    "cbsnews.com",
    "nbcnews.com",
    "sec.gov",
    "federalreserve.gov",
    "fda.gov",
    # 歐洲（英／德／法／歐元區）
    "bbc.com",
    "bbc.co.uk",
    "theguardian.com",
    "telegraph.co.uk",
    "thetimes.com",
    "thetimes.co.uk",
    "news.sky.com",
    "handelsblatt.com",
    "wiwo.de",
    "faz.net",
    "spiegel.de",
    "sueddeutsche.de",
    "dw.com",
    "tagesschau.de",
    "zeit.de",
    "welt.de",
    "lesechos.fr",
    "lemonde.fr",
    "lefigaro.fr",
    "latribune.fr",
    "france24.com",
    "bfmtv.com",
    # 日本
    "nikkei.com",
    "nhk.or.jp",
    "asahi.com",
    "yomiuri.co.jp",
    "mainichi.jp",
    "sankei.com",
    "jiji.com",
    "kyodonews.net",
    "47news.jp",
    "toyokeizai.net",
    "diamond.jp",
    "bloomberg.co.jp",
    # 韓國
    "yna.co.kr",
    "yonhapnewstv.co.kr",
    "einfomax.co.kr",
    "hankyung.com",
    "mk.co.kr",
    "chosun.com",
    "joongang.co.kr",
    "donga.com",
    "sedaily.com",
    "kbs.co.kr",
    "sbs.co.kr",
    "imbc.com",
    "jtbc.co.kr",
    "koreaherald.com",
    "koreatimes.co.kr",
    # 亞太新興（新加坡／印度）與中東全球
    "straitstimes.com",
    "businesstimes.com.sg",
    "channelnewsasia.com",
    "business-standard.com",
    "economictimes.indiatimes.com",
    "livemint.com",
    "thehindu.com",
    "thehindubusinessline.com",
    "ndtv.com",
    "ndtvprofit.com",
    "timesofindia.indiatimes.com",
    "aljazeera.com",
    "arabnews.com",
    "thenationalnews.com",
    # 台灣權威財經媒體與官方機構
    "twse.com.tw",
    "cna.com.tw",
    "money.udn.com",
    "udn.com",
    "ctee.com.tw",
    "cnyes.com",
    "ec.ltn.com.tw",
    "businesstoday.com.tw",
    "businessweekly.com.tw",
    "cw.com.tw",
    "wealth.com.tw",
    "digitimes.com.tw",
    "digitimes.com",
    "technews.tw",
    "bnext.com.tw",
    "moneydj.com",
    "pts.org.tw",
)

CREDIBLE_MEDIA_NAMES = (
    "reuters",
    "bloomberg",
    "wsj",
    "wall street journal",
    "financial times",
    "cnbc",
    "barron's",
    "marketwatch",
    "associated press",
    "ap news",
    "afp",
    "new york times",
    "washington post",
    "the economist",
    "fortune",
    "investor's business daily",
    "morningstar",
    "s&p global",
    "moody's",
    "fitch",
    "bbc",
    "the guardian",
    "the telegraph",
    "handelsblatt",
    "wirtschaftswoche",
    "spiegel",
    "frankfurter allgemeine",
    "les echos",
    "le monde",
    "le figaro",
    "france 24",
    "日本経済新聞",
    "nikkei",
    "nhk",
    "朝日新聞",
    "読売新聞",
    "毎日新聞",
    "時事通信",
    "共同通信",
    "東洋経済",
    "연합뉴스",
    "연합인포맥스",
    "한국경제",
    "매일경제",
    "조선일보",
    "chosunbiz",
    "중앙일보",
    "동아일보",
    "kbs",
    "sbs",
    "mbc",
    "jtbc",
    "straits times",
    "business times",
    "channel newsasia",
    "cna",
    "business standard",
    "economic times",
    "livemint",
    "al jazeera",
    "中央社",
    "經濟日報",
    "工商時報",
    "鉅亨網",
    "自由財經",
    "聯合報",
    "今周刊",
    "商業周刊",
    "天下雜誌",
    "財訊",
    "digitimes",
    "科技新報",
    "數位時代",
    "moneydj",
    "公視",
    "twse",
    "證交所",
)

# 即使是知名大站的子站，也排除娛樂／生活／汽車／軍武／部落格專欄頻道
_DISALLOWED_SUBDOMAINS = (
    "udn.com/news/story/7270",
    "tech.udn.com",
    "style.udn.com",
    "stars.udn.com",
    "health.udn.com",
    "zai.diamond.jp",
    "auto.ltn.com.tw",
    "def.ltn.com.tw",
    "ent.ltn.com.tw",
    "sports.ltn.com.tw",
    "istyle.ltn.com.tw",
    "3c.ltn.com.tw",
    "health.ltn.com.tw",
)

_DISALLOWED_SOURCE_KEYWORDS = (
    "科技玩家",
    "爆料",
    "同學會",
    "網誌",
    "論壇",
    "娛樂",
    "八卦",
    "鉅亨號",
    "汽車頻道",
    "軍武頻道",
    "自由軍武",
    "ザイfx",
)


def _domain_matches(url: str) -> bool:
    if not url:
        return False
    low = url.lower()
    if any(bad in low for bad in _DISALLOWED_SUBDOMAINS):
        return False
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
    except Exception:
        return False
    if not host:
        return False
    return any(host == dom or host.endswith("." + dom) for dom in CREDIBLE_MEDIA_DOMAINS)


def is_credible_media(
    source_name: str = "",
    source_url: str = "",
    link: str = "",
    is_official: bool = False,
    direct_feed: bool = False,
) -> bool:
    """嚴格檢查新聞來源是否屬於具公信力之權威財經媒體或官方公告。"""
    if is_official or direct_feed:
        return True
    name_lo = (source_name or "").strip().lower()
    if name_lo and any(bad in name_lo for bad in _DISALLOWED_SOURCE_KEYWORDS):
        return False
    if _domain_matches(source_url) or _domain_matches(link):
        return True
    if not name_lo:
        return False
    return any(tok in name_lo for tok in CREDIBLE_MEDIA_NAMES)


def _fetch_single_feed(feed: FeedSource, max_items: int = 18, timeout: int = 9) -> List[NewsItem]:
    req = urllib.request.Request(
        feed["url"],
        headers={
            "User-Agent": HTTP_USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw_xml = resp.read()

    root = ET.fromstring(raw_xml)
    items: List[NewsItem] = []

    nodes = root.findall(".//item")
    is_atom = False
    if not nodes:
        nodes = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        is_atom = True

    is_aggregator = "news.google.com" in feed["url"].lower()
    scan_limit = max_items * 3 if is_aggregator else max_items

    for node in nodes[:scan_limit]:
        if is_atom:
            ns = "{http://www.w3.org/2005/Atom}"
            title = _clean_text(node.findtext(f"{ns}title"))
            raw_body = _clean_text(node.findtext(f"{ns}content") or node.findtext(f"{ns}summary"))
            link_el = node.find(f"{ns}link")
            link = (link_el.attrib.get("href", "") if link_el is not None else "").strip()
            pub_raw = node.findtext(f"{ns}updated") or node.findtext(f"{ns}published")
            pub_source_name = ""
            pub_source_url = ""
        else:
            title = _clean_text(node.findtext("title"))
            encoded_body = node.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            desc_body = node.findtext("description")
            raw_body = _clean_text(encoded_body or desc_body)
            link = (node.findtext("link") or "").strip()
            pub_raw = node.findtext("pubDate") or node.findtext("{http://purl.org/dc/elements/1.1/}date")
            src_el = node.find("source")
            pub_source_name = _clean_text(src_el.text) if src_el is not None else ""
            pub_source_url = (src_el.attrib.get("url", "") if src_el is not None else "").strip()

        if not title or len(title) < 6:
            continue

        # Google News 等聚合源一律嚴格審核原始媒體公信力，非白名單媒體直接捨棄
        if is_aggregator:
            if not is_credible_media(
                source_name=pub_source_name,
                source_url=pub_source_url,
                link=link,
                is_official=False,
                direct_feed=False,
            ):
                continue
            resolved_source = pub_source_name or feed["name"]
        else:
            resolved_source = feed["name"]

        full_content = raw_body[:2400] if raw_body else ""
        summary = raw_body
        if summary and title[:24].lower() in summary.lower() and len(summary) < len(title) + 45:
            summary = ""
        if len(summary) > 320:
            summary = summary[:317] + "..."

        item_id = hashlib.md5(f"{title.lower()}|{feed['id']}".encode("utf-8")).hexdigest()[:12]
        items.append(
            NewsItem(
                id=item_id,
                title=title,
                summary=summary,
                full_content=full_content,
                link=link,
                source=resolved_source,
                region=feed["region"],
                macro_region=feed.get("macro_region", "北美"),
                lang=feed["lang"],
                published_at=_parse_pub_date(pub_raw),
                impact_weight=feed["weight"],
            )
        )
        if len(items) >= max_items:
            break
    return items


def _fallback_news() -> List[NewsItem]:
    now = datetime.now(timezone.utc).isoformat()
    samples = [
        ("AI data center capex remains resilient across US hyperscalers", "Offline Snapshot", "美國/華爾街", "北美", "en"),
        ("ECB monitors eurozone inflation and industrial recovery outlook", "Offline Snapshot", "英國/歐洲", "歐洲", "en"),
        ("日銀の金融政策と半導体製造装置輸出に注目が集まる", "Offline Snapshot", "日本/日股", "日本", "ja"),
        ("한국 반도체 수출 호조에도 글로벌 관세 리스크 경계", "Offline Snapshot", "韓國/韓股", "韓國", "ko"),
        ("台積電先進製程產能滿載，AI 伺服器供應鏈營收維持高成長", "離線快照", "台灣/財經", "台灣", "zh"),
    ]
    return [
        NewsItem(
            id=f"offline_{i}",
            title=t,
            summary="",
            link="",
            source=src,
            region=reg,
            macro_region=mreg,
            lang=lang,
            published_at=now,
            impact_weight=1.0,
        )
        for i, (t, src, reg, mreg, lang) in enumerate(samples)
    ]


def _fetch_twse_official_announcements(timeout: int = 8) -> List[NewsItem]:
    """抓取台灣證交所官方重大訊息公告 (t187ap04_L) 與官方市場公告，補齊合約／官方發布消息面。"""
    now_iso = datetime.now(timezone.utc).isoformat()
    out: List[NewsItem] = []

    # 1. 上市公司重大訊息 (合約簽訂、併購、擴產、自結獲利、停工/訴訟等)
    try:
        req = urllib.request.Request(TWSE_MOPS_MATERIAL_URL, headers={"User-Agent": HTTP_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rows = json.loads(resp.read().decode("utf-8", errors="replace"))
        for row in rows[:25]:
            code = str(row.get("公司代號", "")).strip()
            comp = str(row.get("公司名稱", "")).strip()
            subj = _clean_text(row.get("主旨 ") or row.get("主旨"))
            if not subj:
                continue
            title = f"[官方重訊] {comp}({code})：{subj}"
            item_id = hashlib.md5(f"mops|{code}|{subj}".encode("utf-8")).hexdigest()[:12]
            out.append(
                NewsItem(
                    id=item_id,
                    title=title,
                    summary=f"公開資訊觀測站重大訊息（事實發生日：{row.get('事實發生日', '')}）",
                    link="https://mops.twse.com.tw/mops/web/t05sr01_1",
                    source="TWSE 官方重訊公告",
                    region="台灣/官方公告",
                    macro_region="台灣",
                    lang="zh",
                    published_at=now_iso,
                    impact_weight=1.45,
                    is_official=True,
                )
            )
    except Exception:
        pass

    # 2. 證交所官方新聞公告
    try:
        req = urllib.request.Request(TWSE_OFFICIAL_NEWS_URL, headers={"User-Agent": HTTP_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rows = json.loads(resp.read().decode("utf-8", errors="replace"))
        for row in rows[:6]:
            t = _clean_text(row.get("Title"))
            if not t:
                continue
            item_id = hashlib.md5(f"twse_news|{t}".encode("utf-8")).hexdigest()[:12]
            out.append(
                NewsItem(
                    id=item_id,
                    title=f"[證交所公告] {t}",
                    summary="",
                    link=str(row.get("Url") or "").strip(),
                    source="TWSE 證交所官方公告",
                    region="台灣/官方公告",
                    macro_region="台灣",
                    lang="zh",
                    published_at=now_iso,
                    impact_weight=1.35,
                    is_official=True,
                )
            )
    except Exception:
        pass
    return out


def collect_news(
    feeds: List[FeedSource] | None = None,
    max_per_feed: int = 18,
    max_total: int = 260,
) -> Tuple[List[NewsItem], str]:
    """併發抓取全球多語系財經 RSS 與 TWSE 官方重大訊息公告，去重並依全球區域均衡保留情資。"""
    target_feeds = feeds or RSS_FEEDS
    collected: List[NewsItem] = []
    succeeded = 0

    with ThreadPoolExecutor(max_workers=min(14, max(2, len(target_feeds) + 1))) as pool:
        futures = {pool.submit(_fetch_single_feed, f, max_per_feed): f["id"] for f in target_feeds}
        futures[pool.submit(_fetch_twse_official_announcements)] = "twse_official"
        for fut in as_completed(futures):
            try:
                batch = fut.result()
                if batch:
                    collected.extend(batch)
                    succeeded += 1
            except Exception:
                continue

    if not collected:
        return _fallback_news(), "fallback"

    collected.sort(key=lambda x: (1 if x.is_official else 0, x.published_at, x.impact_weight), reverse=True)
    seen_keys = set()
    by_region: Dict[str, List[NewsItem]] = defaultdict(list)

    for item in collected:
        norm = re.sub(r"[\W_]+", "", item.title.lower())[:48]
        if not norm or norm in seen_keys:
            continue
        seen_keys.add(norm)
        by_region[item.macro_region].append(item)

    balanced: List[NewsItem] = []
    region_order = ["北美", "歐洲", "日本", "韓國", "亞太新興", "台灣", "中東全球"]
    for extra in by_region:
        if extra not in region_order:
            region_order.append(extra)

    idx = 0
    while len(balanced) < max_total:
        added_any = False
        for reg in region_order:
            bucket = by_region.get(reg) or []
            if idx < len(bucket):
                balanced.append(bucket[idx])
                added_any = True
                if len(balanced) >= max_total:
                    break
        if not added_any:
            break
        idx += 1

    mode = "live" if succeeded >= max(4, len(target_feeds) // 2) else "partial"
    return balanced, mode


_BOILERPLATE_NEWS_PATTERNS = (
    "stock quote",
    "quote & history",
    "quote, history",
    "quote & news",
    "stock price, news",
    "stock price & news",
    "stock price today",
    "stock price |",
    "stock price (",
    "in real time",
    "check out ",
    "live stock price",
    "price and forecast",
    "stock price forecast",
    "should you buy",
    "buy or sell",
    "is it a buy",
    "stock price prediction",
    "price target &",
    "stock overview",
    "dividend history",
    "stock chart",
    "stock news & quote",
    "做什麼？",
    "是什麼？",
    "股價走勢圖",
    "即時股價",
    "歷史股價",
    "個股資訊",
    "個股概覽",
    "基本資料",
    "懶人包",
    "股市爆料同學會",
    "爆料同學會",
    "討論區",
)

# 台股權證報價短訊（如「長榮元大69購04 緩步升」）不屬於公司基本面／事件新聞
_TW_WARRANT_RE = re.compile(
    r"(元大|凱基|群益|富邦|國泰|統一|永豐|中信|元富|兆豐|康和|台新|國票|華南|日盛)\d{2}[購售]\d{2}"
)

# 容易同名誤判的企業排除規則（例如長榮海運 2603 vs 長榮航 2618）
_COMPANY_CONFLICT_EXCLUSIONS: Dict[str, Tuple[str, ...]] = {
    "2603": ("長榮航", "長榮航空", "長榮鋼", "航空", "搭機", "華航", "機票", "航班"),
    "2609": ("陽明山",),
    "2301": ("光寶科" + "技大",),
}

_STOP_NAME_TOKENS = {
    "inc", "inc.", "corp", "corp.", "corporation", "ltd", "ltd.", "co", "co.",
    "group", "holdings", "company", "technologies", "technology", "international",
    "energy", "financial", "systems", "solutions", "global", "the", "and",
    "applied", "advanced", "american", "united", "general", "national", "bank",
    "first", "next", "new", "capital", "partners", "industries", "manufacturing",
    "electronics", "semiconductor", "semiconductors", "pharma", "pharmaceuticals",
    "medical", "health", "healthcare", "bio", "biotech", "shipping", "marine",
    "airline", "airlines", "power", "electric", "auto", "motors", "communications",
    "networks", "cloud", "data", "digital", "software", "services", "resources",
    "materials", "chemicals", "defense", "aerospace",
}

_US_TIER1_SITE_FILTER = (
    "(site:reuters.com OR site:bloomberg.com OR site:cnbc.com OR site:wsj.com "
    "OR site:ft.com OR site:marketwatch.com OR site:barrons.com OR site:apnews.com "
    "OR site:nytimes.com OR site:investors.com OR site:fortune.com)"
)
_TW_TIER1_SITE_FILTER = (
    "(site:money.udn.com OR site:ctee.com.tw OR site:cna.com.tw OR site:cnyes.com "
    "OR site:ec.ltn.com.tw OR site:moneydj.com OR site:digitimes.com.tw OR site:technews.tw "
    "OR site:businesstoday.com.tw OR site:cw.com.tw OR site:wealth.com.tw)"
)


def is_valid_stock_news(
    item: NewsItem,
    symbol: str,
    name: str = "",
    max_age_days: int = 21,
    require_credible: bool = True,
) -> bool:
    """嚴格驗證新聞是否來自具公信力媒體且真正與該公司相關，並剔除報價頁／SEO預測頁／論壇／權證／誤配公司與過期報導。"""
    title = (item.title or "").strip()
    summary = (item.summary or "").strip()
    if not title:
        return False

    # 0. 必須來自具公信力之權威媒體或官方公告（嚴格阻擋內容農場、論壇、部落格）
    if require_credible and not is_credible_media(
        source_name=item.source,
        link=item.link,
        is_official=item.is_official,
        direct_feed=False,
    ):
        return False

    title_lo = title.lower()
    hay_lo = f"{title} {summary}".lower()

    # 1. 剔除報價入口頁、SEO 預測文、公司簡介懶人包、散戶論壇貼文與權證行情短訊
    if any(pat in title_lo for pat in _BOILERPLATE_NEWS_PATTERNS):
        return False
    if _TW_WARRANT_RE.search(title):
        return False

    # 2. 剔除過期舊聞（超過 max_age_days 天）
    if item.published_at:
        try:
            dt = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
            if age_days > max_age_days:
                return False
        except Exception:
            pass

    code = symbol.strip().upper().split(".")[0]
    code_lo = code.lower()

    # 3. 檢查同名不同公司衝突（如 2603 長榮海運不可收錄長榮航新聞）
    exclusions = _COMPANY_CONFLICT_EXCLUSIONS.get(code, ())
    if exclusions and any(ex in title for ex in exclusions):
        # 除非標題明確同時提到正確代號或全稱（如 2603 / 長榮海運）
        if code not in title and "長榮海運" not in title:
            return False

    # 4. 嚴格邊界比對：標題必須直接出現該股代號（全字比對）或具體公司名稱
    if code.isdigit():
        ticker_hit = bool(re.search(rf"(?<!\d){re.escape(code)}(?!\d)", title))
    else:
        # 美股代號全字邊界比對（至少 2 碼，避免誤命中普通英文單字）
        ticker_hit = len(code_lo) >= 2 and bool(re.search(rf"\b{re.escape(code_lo)}\b", title_lo))

    # 保留括號內的英文簡稱（如 "台積電 (TSMC)" -> ["台積電", "tsmc"]）
    expanded_name = re.sub(r"[()（）]", " ", name or "").strip()
    raw_tokens = [tok.strip().lower() for tok in re.split(r"[\s,/・]+", expanded_name) if tok.strip()]

    # 先檢查雙詞英文全名（如 "applied optoelectronics", "eli lilly", "exxon mobil"）
    en_seq = [t for t in raw_tokens if t.isascii() and t.isalpha() and t not in {"inc", "corp", "corporation", "ltd", "co", "the"}]
    name_hit = False
    if len(en_seq) >= 2:
        full_phrase = " ".join(en_seq[:2])
        if re.search(rf"\b{re.escape(full_phrase)}\b", title_lo):
            name_hit = True

    if not name_hit:
        for tok in raw_tokens:
            if tok in _STOP_NAME_TOKENS or len(tok) < 2:
                continue
            if any("\u4e00" <= ch <= "\u9fff" for ch in tok):
                if tok in title_lo:
                    name_hit = True
                    break
            elif len(tok) >= 4 and re.search(rf"\b{re.escape(tok)}\b", title_lo):
                name_hit = True
                break

    # 若標題沒命中，僅允許台股純數字代號在摘要中明確出現
    if not (ticker_hit or name_hit):
        if code.isdigit():
            return bool(re.search(rf"(?<!\d){re.escape(code)}(?!\d)", hay_lo))
        return False

    return True


def collect_stock_news(
    symbol: str,
    name: str = "",
    market: str = "US",
    max_items: int = 5,
) -> List[NewsItem]:
    """針對單一自選股僅從具公信力權威媒體抓取近 7 日真實新聞（無權威報導則回傳空陣列絕不硬塞）。"""
    import urllib.parse

    code = symbol.strip().upper().split(".")[0]
    clean_name = re.sub(r"[()（）]", " ", name or "").strip()
    exclusions = _COMPANY_CONFLICT_EXCLUSIONS.get(code, ())

    if market == "TW":
        q_parts = [code]
        zh_tokens = [t for t in clean_name.split() if any("\u4e00" <= c <= "\u9fff" for c in t)]
        if zh_tokens:
            q_parts.append(f'"{zh_tokens[0]}"')
        excl_q = " ".join(f'-"{ex}"' for ex in exclusions[:4])
        query = f"({' OR '.join(q_parts)}) {_TW_TIER1_SITE_FILTER} {excl_q} when:7d".strip()
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed: FeedSource = {
            "id": f"stock_{code}",
            "name": f"{zh_tokens[0] if zh_tokens else code} 權威個股快訊",
            "region": "台灣/個股",
            "macro_region": "台灣",
            "lang": "zh",
            "url": url,
            "weight": 1.3,
        }
    else:
        en_words = [
            w for w in re.split(r"[\s,/・]+", clean_name)
            if w.isascii() and w.isalpha() and len(w) >= 3 and w.lower() not in {"inc", "corp", "corporation", "ltd", "co", "the"}
        ]
        q_parts = [f'"{code}"']
        if len(en_words) >= 2:
            q_parts.append(f'"{" ".join(en_words[:2])}"')
        elif en_words and en_words[0].lower() not in _STOP_NAME_TOKENS:
            q_parts.append(f'"{en_words[0]}"')
        query = (
            f"({' OR '.join(q_parts)}) {_US_TIER1_SITE_FILTER} "
            f'-"stock quote" -"price forecast" -"should you buy" -"in real time" when:7d'
        )
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        feed = {
            "id": f"stock_{code}",
            "name": f"{code} 權威個股快訊",
            "region": "美國/個股",
            "macro_region": "北美",
            "lang": "en",
            "url": url,
            "weight": 1.3,
        }

    raw_items = _fetch_single_feed(feed, max_items=max_items * 3)
    seen = set()
    valid: List[NewsItem] = []
    for it in raw_items:
        if not is_valid_stock_news(it, symbol, name=name, max_age_days=14, require_credible=True):
            continue
        norm = re.sub(r"[\W_]+", "", it.title.lower())[:48]
        if norm and norm not in seen:
            seen.add(norm)
            valid.append(it)
            if len(valid) >= max_items:
                break
    return valid
