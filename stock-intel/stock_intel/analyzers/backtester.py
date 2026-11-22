"""量化策略回測引擎：以歷史日線 OHLCV 驗證多空策略績效（含真實交易手續費／證交稅、無未來函數）。"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from stock_intel.analyzers.technical import _ema, _rsi, _sma


def _max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak > 0, peak, 1.0)
    return round(float(np.min(dd)) * 100.0, 2)


def _sharpe(equity: np.ndarray) -> float:
    if len(equity) < 10:
        return 0.0
    rets = np.diff(equity) / np.where(equity[:-1] > 0, equity[:-1], 1.0)
    std = float(np.std(rets))
    if std <= 1e-9:
        return 0.0
    return round(float(np.mean(rets)) / std * math.sqrt(252.0), 2)


def _cagr(start_nav: float, end_nav: float, trading_days: int) -> float:
    if start_nav <= 0 or end_nav <= 0 or trading_days <= 5:
        return 0.0
    years = trading_days / 252.0
    return round(((end_nav / start_nav) ** (1.0 / years) - 1.0) * 100.0, 2)


def _simulate_signals(
    closes: np.ndarray,
    dates: List[str],
    entries: np.ndarray,
    exits: np.ndarray,
    buy_cost: float,
    sell_cost: float,
    stop_loss_pct: float = 0.08,
    start_idx: int = 60,
) -> Dict[str, Any]:
    """逐日模擬多頭策略執行（收盤確認訊號並以該收盤價計入交易成本），計算完整績效指標。"""
    n = len(closes)
    nav = 1.0
    in_pos = False
    entry_price = 0.0
    peak_price = 0.0
    nav_series: List[float] = []
    trade_returns: List[float] = []

    for i in range(start_idx, n):
        price = float(closes[i])
        if in_pos:
            # 依昨日收盤至今日收盤更新淨值
            prev_p = float(closes[i - 1])
            if prev_p > 0:
                nav *= price / prev_p
            if price > peak_price:
                peak_price = price

            hit_trailing_stop = peak_price > 0 and (price <= peak_price * (1.0 - stop_loss_pct))
            if exits[i] or hit_trailing_stop:
                nav *= 1.0 - sell_cost
                gross_ret = (price * (1.0 - sell_cost)) / (entry_price * (1.0 + buy_cost)) - 1.0
                trade_returns.append(gross_ret)
                in_pos = False
                entry_price = 0.0
                peak_price = 0.0
        else:
            if entries[i]:
                nav *= 1.0 - buy_cost
                in_pos = True
                entry_price = price
                peak_price = price

        nav_series.append(nav)

    # 若結束時仍持倉，計算未實現交易損益以反映真實勝率（不強制扣出場費）
    if in_pos and entry_price > 0:
        last_p = float(closes[-1])
        trade_returns.append(last_p / (entry_price * (1.0 + buy_cost)) - 1.0)

    eq = np.array(nav_series, dtype=float)
    eval_days = len(eq)
    total_ret = round((float(eq[-1]) - 1.0) * 100.0, 2) if eval_days else 0.0

    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r <= 0]
    win_rate = round(len(wins) / len(trade_returns) * 100.0, 1) if trade_returns else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 1e-9 else (round(gross_win * 10.0, 2) if gross_win > 0 else 0.0)

    # 抽樣約 50 個時間點供前端繪製策略淨值 vs 買進持有曲線
    bh_base = float(closes[start_idx]) if closes[start_idx] > 0 else 1.0
    bh_eq = closes[start_idx:] / bh_base
    step = max(1, eval_days // 48)
    curve: List[Dict[str, Any]] = []
    for k in range(0, eval_days, step):
        curve.append(
            {
                "date": dates[start_idx + k],
                "strategy": round(float(eq[k]) * 100.0, 2),
                "buyhold": round(float(bh_eq[k]) * 100.0, 2),
            }
        )
    if eval_days > 0 and (not curve or curve[-1]["date"] != dates[-1]):
        curve.append(
            {
                "date": dates[-1],
                "strategy": round(float(eq[-1]) * 100.0, 2),
                "buyhold": round(float(bh_eq[-1]) * 100.0, 2),
            }
        )

    return {
        "total_return_pct": total_ret,
        "cagr_pct": _cagr(1.0, float(eq[-1]) if eval_days else 1.0, eval_days),
        "max_drawdown_pct": _max_drawdown(eq),
        "sharpe_ratio": _sharpe(eq),
        "win_rate_pct": win_rate,
        "profit_factor": min(99.0, profit_factor),
        "trade_count": len(trade_returns),
        "current_signal": "持有偏多" if in_pos else "空手觀望",
        "equity_curve": curve,
    }


def run_stock_backtest(chart_data: Dict[str, Any], market: str = "US") -> Optional[Dict[str, Any]]:
    """
    針對單檔個股執行 3 套量化交易策略回測，並與買進持有基準對比。
    建議傳入 1 年～2 年日線資料（至少 90 個交易日）。
    """
    bars: List[Dict[str, Any]] = chart_data.get("bars") or []
    if len(bars) < 85:
        return None

    dates = [b["date"] for b in bars]
    closes = np.array([b["close"] for b in bars], dtype=float)
    vols = np.array([b["volume"] for b in bars], dtype=float)
    n = len(closes)
    start_idx = 60

    # 市場真實單邊交易成本：台股手續費 0.1425% + 賣出證交稅 0.3%；美股估 0.10% 滑價
    if market == "TW":
        buy_cost, sell_cost = 0.001425, 0.004425
    else:
        buy_cost, sell_cost = 0.001, 0.001

    ma5 = _sma(closes, 5)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)
    vol_ma20 = _sma(vols, 20)
    rsi14 = _rsi(closes, 14)

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    macd_sig = _ema(macd_line, 9)
    macd_hist = macd_line - macd_sig

    # 基準：買進持有 (Buy & Hold)
    bh_eq = closes[start_idx:] / (closes[start_idx] if closes[start_idx] > 0 else 1.0)
    eval_days = len(bh_eq)
    bh_ret = round((float(bh_eq[-1]) - 1.0) * 100.0, 2)
    bh_cagr = _cagr(1.0, float(bh_eq[-1]), eval_days)
    bh_mdd = _max_drawdown(bh_eq)
    bh_sharpe = _sharpe(bh_eq)

    # 策略 1：均線多頭趨勢策略 (MA5 > MA20 且站上 MA60 進場；跌破 MA20 或 8% 移動停損出場)
    s1_ent = np.zeros(n, dtype=bool)
    s1_ext = np.zeros(n, dtype=bool)
    for i in range(start_idx, n):
        if not (np.isnan(ma5[i]) or np.isnan(ma20[i]) or np.isnan(ma60[i])):
            if ma5[i] > ma20[i] and closes[i] > ma60[i]:
                s1_ent[i] = True
            if ma5[i] < ma20[i] and closes[i] < ma20[i]:
                s1_ext[i] = True

    # 策略 2：RSI + MACD 動能反轉複合策略 (MACD 翻強或超賣反彈進場；高檔過熱或跌破月線轉空出場)
    s2_ent = np.zeros(n, dtype=bool)
    s2_ext = np.zeros(n, dtype=bool)
    for i in range(start_idx, n):
        if np.isnan(rsi14[i]) or np.isnan(ma20[i]):
            continue
        macd_turn_up = macd_hist[i] > 0 and macd_hist[i] >= macd_hist[i - 1]
        rsi_rebound = rsi14[i - 1] < 36 and rsi14[i] >= rsi14[i - 1] + 2.0
        if (macd_turn_up and rsi14[i] < 68) or rsi_rebound:
            s2_ent[i] = True
        if rsi14[i] > 78 or (macd_hist[i] < 0 and closes[i] < ma20[i]):
            s2_ext[i] = True

    # 策略 3：智策綜合技術評分策略 (結合均線架構 + MACD + RSI + 量能確認)
    s3_ent = np.zeros(n, dtype=bool)
    s3_ext = np.zeros(n, dtype=bool)
    for i in range(start_idx, n):
        if np.isnan(ma60[i]) or np.isnan(rsi14[i]):
            continue
        sc = 50.0
        if closes[i] > ma5[i] > ma20[i] > ma60[i]:
            sc += 18
        elif closes[i] > ma20[i] and closes[i] > ma60[i]:
            sc += 10
        elif closes[i] < ma20[i] and closes[i] < ma60[i]:
            sc -= 14

        if macd_hist[i] > 0 and macd_hist[i] >= macd_hist[i - 1]:
            sc += 10
        elif macd_hist[i] < 0 and macd_hist[i] < macd_hist[i - 1]:
            sc -= 10

        if 50 <= rsi14[i] <= 68:
            sc += 7
        elif rsi14[i] < 32:
            sc += 4  # 超賣保護
        elif rsi14[i] > 76:
            sc -= 8

        if not np.isnan(vol_ma20[i]) and vol_ma20[i] > 0:
            v_ratio = vols[i] / vol_ma20[i]
            if v_ratio > 1.25 and closes[i] > closes[i - 1]:
                sc += 5
            elif v_ratio > 1.35 and closes[i] < closes[i - 1]:
                sc -= 7

        if sc >= 62:
            s3_ent[i] = True
        elif sc <= 42:
            s3_ext[i] = True

    defs = [
        ("ma_trend", "均線多頭趨勢策略 (MA5/20/60)", s1_ent, s1_ext, 0.08),
        ("rsi_macd", "RSI+MACD 動能反轉策略", s2_ent, s2_ext, 0.07),
        ("composite_quant", "智策綜合技術評分策略", s3_ent, s3_ext, 0.08),
    ]

    strategies: List[Dict[str, Any]] = []
    for sid, sname, ent, ext, sl in defs:
        res = _simulate_signals(closes, dates, ent, ext, buy_cost, sell_cost, sl, start_idx)
        res["id"] = sid
        res["name"] = sname
        res["alpha_pct"] = round(res["total_return_pct"] - bh_ret, 2)
        strategies.append(res)

    # 依風險調整後報酬（夏普比率優先，再看總報酬與最大回撤）選出最佳策略
    best = max(
        strategies,
        key=lambda x: (x["sharpe_ratio"] * 20.0 + x["total_return_pct"] * 0.4 + x["max_drawdown_pct"] * 0.3),
    )

    return {
        "start_date": dates[start_idx],
        "end_date": dates[-1],
        "trading_days": eval_days,
        "fee_model": "台股(手續費0.1425%+證交稅0.3%)" if market == "TW" else "美股(單邊滑價0.10%)",
        "benchmark_return_pct": bh_ret,
        "benchmark_cagr_pct": bh_cagr,
        "benchmark_max_drawdown_pct": bh_mdd,
        "benchmark_sharpe": bh_sharpe,
        "best_strategy_id": best["id"],
        "best_strategy_name": best["name"],
        "best_total_return_pct": best["total_return_pct"],
        "best_alpha_pct": best["alpha_pct"],
        "best_max_drawdown_pct": best["max_drawdown_pct"],
        "best_sharpe": best["sharpe_ratio"],
        "best_win_rate_pct": best["win_rate_pct"],
        "best_current_signal": best["current_signal"],
        "strategies": strategies,
    }
