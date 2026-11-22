"""混合式 LLM 深度財經推演模組：支援 Gemini / OpenAI REST API（無需額外 SDK，無 Key 自動降級為本地引擎）。"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

from stock_intel.models import MacroOutlook, NewsItem, SectorOutlook


def _build_prompt(
    macro: MacroOutlook,
    sectors: List[SectorOutlook],
    news_items: List[NewsItem],
) -> str:
    top_news = "\n".join(
        f"- [{n.source} | {n.sentiment_label}({n.sentiment_score:+.2f})] {n.title}"
        for n in news_items[:28]
    )
    bm_lines = "\n".join(
        f"- {b.name}: {b.price} (1D {b.change_pct_1d:+.2f}%, 5D {b.change_pct_5d:+.2f}%, 1M {b.change_pct_1m:+.2f}%)"
        for b in macro.benchmarks
    )
    sec_lines = "\n".join(
        f"- {s.name}: 量化評分 {s.score}/100 ({s.outlook_label}), 新聞情緒 {s.news_score:+.1f}"
        for s in sectors
    )
    return (
        "你是一位專精於美股與台股跨市場聯動的資深首席投資策略師。"
        "請根據以下最新國際與台灣財經新聞、跨市場指數與產業量化分數，進行嚴謹的利多／利空因果推演。\n\n"
        f"【最新大盤與風險指標】\n{bm_lines}\n\n"
        f"【量化初判】\n綜合多空分數: {macro.overall_score:+.1f} ({macro.stance})\n\n"
        f"【產業量化排行】\n{sec_lines}\n\n"
        f"【最新財經頭條】\n{top_news}\n\n"
        "請務必以純 JSON 格式回覆（不要加 markdown 圍欄），包含以下欄位：\n"
        "{\n"
        '  "executive_summary": "120字以內繁體中文總結當前國際情勢對美股與台股走向屬於利多還是利空、核心原因為何",\n'
        '  "llm_commentary": "200字以內深度策略點評，說明跨市場資金輪動邏輯與最值得關注的利多產業",\n'
        '  "bullish_catalysts": ["利多催化1", "利多催化2", "利多催化3"],\n'
        '  "bearish_risks": ["利空風險1", "利空風險2", "利空風險3"],\n'
        '  "action_plan": ["具體操作建議1", "具體操作建議2", "具體操作建議3"]\n'
        "}"
    )


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except Exception:
        return None


def _call_gemini(prompt: str, api_key: str, model: str) -> Optional[Dict[str, Any]]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    text = "".join(p.get("text", "") for p in parts)
    return _extract_json(text)


def _call_openai(prompt: str, api_key: str, model: str) -> Optional[Dict[str, Any]]:
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "你是資深美股與台股策略分析師，請以繁體中文輸出嚴謹 JSON。"},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choices = data.get("choices") or []
    if not choices:
        return None
    text = (choices[0].get("message") or {}).get("content", "")
    return _extract_json(text)


def enhance_with_llm(
    macro: MacroOutlook,
    sectors: List[SectorOutlook],
    news_items: List[NewsItem],
) -> MacroOutlook:
    """
    若環境變數已設定 GEMINI_API_KEY 或 OPENAI_API_KEY，則自動調用 LLM 強化推演；
    否則維持本地量化推演結果，確保系統零門檻直接可用。
    """
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    if provider == "local":
        return macro

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    prompt = _build_prompt(macro, sectors, news_items)

    result: Optional[Dict[str, Any]] = None
    used_engine = "local_quant"

    try:
        if provider in ("auto", "gemini") and gemini_key:
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
            result = _call_gemini(prompt, gemini_key, model)
            if result:
                used_engine = f"gemini ({model})"
        if result is None and provider in ("auto", "openai") and openai_key:
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
            result = _call_openai(prompt, openai_key, model)
            if result:
                used_engine = f"openai ({model})"
    except Exception:
        result = None

    if not result:
        return macro

    macro.analysis_engine = used_engine
    if isinstance(result.get("executive_summary"), str) and result["executive_summary"].strip():
        macro.executive_summary = result["executive_summary"].strip()
    if isinstance(result.get("llm_commentary"), str) and result["llm_commentary"].strip():
        macro.llm_commentary = result["llm_commentary"].strip()
    for field_name in ("bullish_catalysts", "bearish_risks", "action_plan"):
        vals = result.get(field_name)
        if isinstance(vals, list) and vals:
            setattr(macro, field_name, [str(v).strip() for v in vals if str(v).strip()][:5])
    return macro
