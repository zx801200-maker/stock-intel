"""FastAPI 網頁伺服器：提供即時分析、個股診斷、策略回測與推播測試 REST API。"""

from __future__ import annotations

import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from stock_intel.analyzers.pipeline import StockIntelPipeline
from stock_intel.collectors.article_reader import extract_article_content
from stock_intel.notifications.notifier import dispatch_notifications
from stock_intel.storage.cache import ReportStore

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Stock Intel 智策股市情報與多空推演系統",
    version="2.0.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_store = ReportStore()
_pipeline = StockIntelPipeline(store=_store)
_refresh_lock = threading.Lock()
_cached_report: Optional[Dict[str, Any]] = None


def _get_or_compute_report(force_refresh: bool = False) -> Dict[str, Any]:
    global _cached_report
    ttl = int(os.getenv("CACHE_TTL_MINUTES", "30") or "30")

    if not force_refresh:
        if _cached_report is not None:
            return _cached_report
        stored = _store.load_latest(max_age_minutes=ttl)
        if stored is not None:
            _cached_report = stored
            return stored

    with _refresh_lock:
        if not force_refresh and _cached_report is not None:
            return _cached_report
        report = _pipeline.run_full_analysis(save_to_db=True)
        _cached_report = report.to_dict()
        return _cached_report


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": "2.0.0",
        "llm_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")),
        "push_channels": {
            "line": bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN")),
            "line_mode": "push" if os.getenv("LINE_USER_ID") else "broadcast",
            "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
            "discord": bool(os.getenv("DISCORD_WEBHOOK_URL")),
            "email": bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("EMAIL_TO")),
        },
        "has_cached_report": _cached_report is not None or _store.load_latest() is not None,
    }


@app.get("/api/report")
def get_report(force: bool = Query(default=False, description="是否強制重新抓取全球最新情資")) -> JSONResponse:
    data = _get_or_compute_report(force_refresh=force)
    return JSONResponse(content=data)


@app.post("/api/refresh")
def refresh_report() -> JSONResponse:
    data = _get_or_compute_report(force_refresh=True)
    return JSONResponse(content=data)


@app.get("/api/history")
def get_history(limit: int = Query(default=15, ge=1, le=60)) -> Dict[str, Any]:
    return {"items": _store.get_history(limit=limit)}


@app.get("/api/stock/{symbol}")
def analyze_stock(symbol: str) -> JSONResponse:
    """即時分析任意美股或台股代號（含基本面、技術面、三大法人買賣超與 2 年期策略回測）。"""
    clean = symbol.strip()
    if not clean or len(clean) > 16:
        raise HTTPException(status_code=400, detail="無效的股票代號格式")

    report = _cached_report or _store.load_latest()
    sector_scores = {
        s["sector_id"]: s["score"] for s in (report.get("sectors") or [])
    } if report else {}

    result = _pipeline.analyze_single_stock(clean, sector_scores=sector_scores)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"無法取得 {clean} 的即時行情資料，請確認代號（台股輸入如 2330 或 2330.TW，美股輸入如 NVDA）。",
        )
    return JSONResponse(content=asdict(result))


@app.post("/api/notify")
def trigger_notify(
    session: str = Query(default="daily", description="tw_premarket | us_premarket | daily"),
    dry_run: bool = Query(default=True, description="True 僅預覽簡報不發送外部訊息"),
) -> JSONResponse:
    data = _get_or_compute_report(force_refresh=False)
    res = dispatch_notifications(data, session=session, dry_run=dry_run)
    return JSONResponse(content=res)


@app.get("/api/article")
def fetch_article(url: str = Query(..., description="新聞來源網址")) -> JSONResponse:
    """點擊消息面新聞時即時抓取完整報導正文與最終來源網址，方便人工驗證。"""
    res = extract_article_content(url, timeout=8, max_chars=5200)
    return JSONResponse(content=res)


@app.get("/api/watchlist")
def get_watchlist() -> JSONResponse:
    """取得使用者自選股清單（含已分析之即時報價、基本面、技術面、信用風險與回測資料）。"""
    items = _store.list_watchlist()
    report = _cached_report or _store.load_latest()
    stock_map = {s["symbol"].upper(): s for s in ((report or {}).get("stocks") or [])}
    enriched = []
    for it in items:
        sym = it["symbol"].upper()
        st = stock_map.get(sym)
        enriched.append({**it, "stock": st})
    return JSONResponse(content={"items": enriched})


@app.post("/api/watchlist")
async def add_to_watchlist(request: Request) -> JSONResponse:
    """新增美股或台股至自選股清單，並即時抓取完整診斷資料。"""
    body = await request.json()
    raw_sym = str(body.get("symbol") or "").strip()
    note = str(body.get("note") or "").strip()[:160]
    if not raw_sym or len(raw_sym) > 16:
        raise HTTPException(status_code=400, detail="請輸入有效的股票代號（如 NVDA 或 2330）")

    norm_sym, market = _pipeline.collector.normalize_symbol(raw_sym)
    report = _cached_report or _store.load_latest()
    stock_map = {s["symbol"].upper(): s for s in ((report or {}).get("stocks") or [])}
    st_dict = stock_map.get(norm_sym)

    if st_dict is None:
        sector_scores = {
            s["sector_id"]: s["score"] for s in ((report or {}).get("sectors") or [])
        }
        st_obj = _pipeline.analyze_single_stock(raw_sym, sector_scores=sector_scores)
        if st_obj is None:
            raise HTTPException(
                status_code=404,
                detail=f"找不到代號 {raw_sym} 的行情資料，請確認美股代號（如 TSLA）或台股代號（如 2330）。",
            )
        st_dict = asdict(st_obj)
        norm_sym = st_dict["symbol"].upper()
        market = st_dict["market"]

    saved = _store.add_watchlist(
        symbol=norm_sym,
        name=st_dict.get("name") or norm_sym,
        market=market,
        note=note,
    )
    if _cached_report is not None:
        _cached_report["watchlist"] = _store.list_watchlist()
        if not any(s["symbol"].upper() == norm_sym for s in _cached_report.get("stocks") or []):
            _cached_report["stocks"].append(st_dict)

    return JSONResponse(content={"item": saved, "stock": st_dict})


@app.patch("/api/watchlist/{symbol}")
async def patch_watchlist_note(symbol: str, request: Request) -> JSONResponse:
    """更新自選股的個人投資備忘（如目標價、觀察重點）。"""
    body = await request.json()
    note = str(body.get("note") or "").strip()[:160]
    norm_sym, _ = _pipeline.collector.normalize_symbol(symbol)
    ok = _store.update_watchlist_note(symbol, note) or _store.update_watchlist_note(norm_sym, note)
    if not ok:
        raise HTTPException(status_code=404, detail=f"自選股清單中找不到 {symbol}")
    if _cached_report is not None:
        _cached_report["watchlist"] = _store.list_watchlist()
    return JSONResponse(content={"ok": True, "symbol": norm_sym, "note": note})


@app.delete("/api/watchlist/{symbol}")
def delete_from_watchlist(symbol: str) -> JSONResponse:
    """自自選股清單移除標的。"""
    norm_sym, _ = _pipeline.collector.normalize_symbol(symbol)
    ok = _store.remove_watchlist(symbol) or _store.remove_watchlist(norm_sym)
    if not ok:
        raise HTTPException(status_code=404, detail=f"自選股清單中找不到 {symbol}")
    if _cached_report is not None:
        _cached_report["watchlist"] = _store.list_watchlist()
    return JSONResponse(content={"ok": True, "symbol": norm_sym})


@app.post("/api/line/webhook")
async def line_webhook(request: Request) -> Dict[str, Any]:
    """輔助接收 LINE Webhook 事件，協助快速查詢個人 userId 或群組 groupId。"""
    body = await request.json()
    discovered = []
    for ev in body.get("events") or []:
        src = ev.get("source") or {}
        discovered.append(
            {
                "type": src.get("type"),
                "userId": src.get("userId"),
                "groupId": src.get("groupId"),
                "roomId": src.get("roomId"),
            }
        )
    if discovered:
        print(f"[LINE Webhook] 偵測到來源 ID：{discovered}")
    return {"status": "ok", "sources": discovered}
