"""SQLite 儲存引擎：快取最新市場報告並記錄歷史多空推演軌跡。"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from stock_intel.config import BASE_DIR, DATA_DIR, DB_PATH


class ReportStore:
    def __init__(self, db_path: Path | None = None, seed_watchlist: bool | None = None) -> None:
        self._is_default_db = db_path is None
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()
        should_seed = self._is_default_db if seed_watchlist is None else seed_watchlist
        if should_seed:
            self._seed_watchlist_if_empty()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TEXT NOT NULL,
                    data_mode TEXT NOT NULL,
                    overall_score REAL NOT NULL,
                    stance TEXT NOT NULL,
                    top_sector TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reports_generated_at
                ON reports(generated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    market TEXT NOT NULL DEFAULT 'US',
                    note TEXT NOT NULL DEFAULT '',
                    added_at TEXT NOT NULL
                )
                """
            )

    def _seed_watchlist_if_empty(self) -> None:
        """若本機資料庫尚未有自選股（例如 GitHub Actions 全新執行環境），自動載入 watchlist.json 與 WATCHLIST_SYMBOLS。"""
        with self._connect() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        if cnt == 0:
            seed_path = BASE_DIR / "watchlist.json"
            if seed_path.exists():
                try:
                    items = json.loads(seed_path.read_text(encoding="utf-8"))
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and item.get("symbol"):
                                self.add_watchlist(
                                    symbol=str(item["symbol"]),
                                    name=str(item.get("name") or ""),
                                    market=str(item.get("market") or "US"),
                                    note=str(item.get("note") or ""),
                                )
                            elif isinstance(item, str) and item.strip():
                                raw = item.strip().upper()
                                mkt = "TW" if raw.endswith(".TW") or raw.isdigit() else "US"
                                sym = f"{raw}.TW" if raw.isdigit() else raw
                                self.add_watchlist(symbol=sym, market=mkt)
                except Exception:
                    pass
        env_syms = os.getenv("WATCHLIST_SYMBOLS", "").strip()
        if env_syms:
            for part in env_syms.replace(";", ",").split(","):
                raw = part.strip().upper()
                if not raw:
                    continue
                mkt = "TW" if raw.endswith(".TW") or raw.isdigit() else "US"
                sym = f"{raw}.TW" if raw.isdigit() else raw
                self.add_watchlist(symbol=sym, market=mkt)

    def save_report(self, report_dict: Dict[str, Any]) -> None:
        macro = report_dict.get("macro") or {}
        sectors = report_dict.get("sectors") or []
        top_sector = sectors[0]["name"] if sectors else ""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (generated_at, data_mode, overall_score, stance, top_sector, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report_dict.get("generated_at", datetime.now(timezone.utc).isoformat()),
                    report_dict.get("data_mode", "live"),
                    float(macro.get("overall_score", 0.0)),
                    str(macro.get("stance", "震盪中性")),
                    top_sector,
                    json.dumps(report_dict, ensure_ascii=False),
                ),
            )

    def load_latest(self, max_age_minutes: Optional[int] = None) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT generated_at, payload_json FROM reports ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        if max_age_minutes is not None:
            try:
                ts = datetime.fromisoformat(row["generated_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - ts > timedelta(minutes=max_age_minutes):
                    return None
            except Exception:
                return None
        try:
            return json.loads(row["payload_json"])
        except Exception:
            return None

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT generated_at, data_mode, overall_score, stance, top_sector
                FROM reports
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---- 自選股清單 CRUD ----
    def list_watchlist(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, name, market, note, added_at
                FROM watchlist
                ORDER BY added_at DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def add_watchlist(
        self,
        symbol: str,
        name: str = "",
        market: str = "US",
        note: str = "",
    ) -> Dict[str, Any]:
        sym = symbol.strip().upper()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT symbol, name, market, note, added_at FROM watchlist WHERE symbol = ?",
                (sym,),
            ).fetchone()
            if existing:
                new_name = name or existing["name"]
                new_market = market or existing["market"]
                new_note = note if note != "" else existing["note"]
                conn.execute(
                    "UPDATE watchlist SET name = ?, market = ?, note = ? WHERE symbol = ?",
                    (new_name, new_market, new_note, sym),
                )
                return {
                    "symbol": sym,
                    "name": new_name,
                    "market": new_market,
                    "note": new_note,
                    "added_at": existing["added_at"],
                }
            conn.execute(
                """
                INSERT INTO watchlist (symbol, name, market, note, added_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sym, name, market, note, now),
            )
        return {"symbol": sym, "name": name, "market": market, "note": note, "added_at": now}

    def update_watchlist_note(self, symbol: str, note: str) -> bool:
        sym = symbol.strip().upper()
        with self._connect() as conn:
            cur = conn.execute("UPDATE watchlist SET note = ? WHERE symbol = ?", (note, sym))
            return cur.rowcount > 0

    def remove_watchlist(self, symbol: str) -> bool:
        sym = symbol.strip().upper()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM watchlist WHERE symbol = ?", (sym,))
            return cur.rowcount > 0
