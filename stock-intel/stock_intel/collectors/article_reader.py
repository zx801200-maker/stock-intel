"""完整報導內文即時擷取器（使用 lxml 智慧抽取文章正文段落，供人工驗證與離線閱讀）。"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Set

from lxml import html as lhtml

from stock_intel.config import HTTP_USER_AGENT

_WS_RE = re.compile(r"\s+")
_NOISE_PATTERNS = (
    "cookie", "subscribe", "sign in", "log in", "all rights reserved",
    "advertisement", "javascript", "privacy policy", "terms of service",
    "訂閱", "登入", "隱私權", "版權所有", "廣告",
)


def _is_safe_public_url(url: str) -> bool:
    """僅允許公開 HTTP(S) 網址，阻擋本機／內網位址以防止 SSRF。"""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
            return False
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(host))
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except Exception:
            pass
        return True
    except Exception:
        return False


def _clean_para(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def extract_article_content(url: str, timeout: int = 7, max_chars: int = 4800) -> Dict[str, Any]:
    """抓取新聞原網址並抽取完整報導段落與真實來源網域。"""
    clean_url = (url or "").strip()
    if not clean_url:
        return {"ok": False, "url": "", "error": "此筆情資未附帶來源網址"}

    parsed = urllib.parse.urlparse(clean_url)
    domain = parsed.netloc.lower().replace("www.", "")

    if "news.google.com" in domain:
        return {
            "ok": False,
            "url": clean_url,
            "final_url": clean_url,
            "domain": "news.google.com",
            "paragraphs": [],
            "full_text": "",
            "note": "此連結為 Google News 轉址頁面（需由瀏覽器跳轉至原始媒體），請點擊下方「前往來源網站人工驗證」直接開啟完整原報導。",
        }

    if not _is_safe_public_url(clean_url):
        return {"ok": False, "url": clean_url, "error": "不支援或不安全的網址格式"}

    try:
        req = urllib.request.Request(
            clean_url,
            headers={
                "User-Agent": HTTP_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            raw_bytes = resp.read(700_000)  # 限制讀取 700KB 防止過大檔案
        html_text = raw_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        return {
            "ok": False,
            "url": clean_url,
            "final_url": clean_url,
            "domain": domain,
            "paragraphs": [],
            "full_text": "",
            "note": f"來源網站暫時無法自動擷取全文（{exc}），請點擊下方按鈕直接開啟原網站人工驗證。",
        }

    final_domain = urllib.parse.urlparse(final_url).netloc.lower().replace("www.", "")
    try:
        doc = lhtml.fromstring(html_text)
    except Exception:
        return {
            "ok": False,
            "url": clean_url,
            "final_url": final_url,
            "domain": final_domain,
            "paragraphs": [],
            "full_text": "",
            "note": "無法解析網頁內容，請點擊來源連結直接檢視。",
        }

    title = ""
    t_nodes = doc.xpath("//meta[@property='og:title']/@content | //title/text()")
    if t_nodes:
        title = _clean_para(str(t_nodes[0]))

    og_desc = ""
    d_nodes = doc.xpath("//meta[@property='og:description']/@content | //meta[@name='description']/@content")
    if d_nodes:
        og_desc = _clean_para(str(d_nodes[0]))

    # 移除腳本、導覽列、頁尾與側邊欄雜訊
    for bad in doc.xpath("//script|//style|//noscript|//nav|//header|//footer|//aside|//form"):
        bad.drop_tree()

    raw_nodes = doc.xpath("//article//p | //main//p")
    if len(raw_nodes) < 3:
        raw_nodes = doc.xpath("//p")

    paragraphs: List[str] = []
    seen: Set[str] = set()
    total_len = 0

    for node in raw_nodes:
        txt = _clean_para(node.text_content())
        if len(txt) < 28:
            continue
        low = txt.lower()
        if any(np in low for np in _NOISE_PATTERNS) and len(txt) < 120:
            continue
        if txt in seen:
            continue
        seen.add(txt)
        paragraphs.append(txt)
        total_len += len(txt)
        if total_len >= max_chars or len(paragraphs) >= 16:
            break

    if not paragraphs and og_desc:
        paragraphs = [og_desc]

    full_text = "\n\n".join(paragraphs)
    note = "" if paragraphs else "來源網站可能啟用付費牆或動態載入，請點擊「前往來源網站人工驗證」直接開啟原報導。"

    return {
        "ok": bool(paragraphs),
        "url": clean_url,
        "final_url": final_url,
        "domain": final_domain,
        "title": title,
        "paragraphs": paragraphs,
        "full_text": full_text,
        "note": note,
    }


def enrich_sector_catalysts_content(sectors: List[Any], max_fetch: int = 12) -> None:
    """併發預先擷取各產業最關鍵催化報導的完整內文（跳過 Google News JS 轉址以維持速度）。"""
    targets: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()

    for sec in sectors:
        for group in (sec.bullish_catalysts_news, sec.bearish_catalysts_news):
            for item in group[:2]:
                url = str(item.get("link") or "").strip()
                if not url or url in seen_urls or "news.google.com" in url:
                    continue
                if item.get("full_content") and len(str(item["full_content"])) > 450:
                    continue
                seen_urls.add(url)
                targets.append(item)
                if len(targets) >= max_fetch:
                    break
            if len(targets) >= max_fetch:
                break
        if len(targets) >= max_fetch:
            break

    if not targets:
        return

    with ThreadPoolExecutor(max_workers=min(6, len(targets))) as pool:
        futs = {pool.submit(extract_article_content, str(it["link"]), 5, 2400): it for it in targets}
        for fut in as_completed(futs):
            item = futs[fut]
            try:
                res = fut.result()
                if res.get("ok") and res.get("full_text"):
                    item["full_content"] = res["full_text"]
                    item["final_url"] = res.get("final_url") or item.get("link")
                    item["domain"] = res.get("domain") or ""
            except Exception:
                continue
