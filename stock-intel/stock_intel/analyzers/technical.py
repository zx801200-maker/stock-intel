"""技術面量化分析引擎：均線、RSI、MACD、布林通道、KD、量能與支撐壓力，自動條列技術面優劣勢。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from stock_intel.models import TechnicalAnalysis


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def _sma(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=float)
    if len(values) < period:
        return out
    csum = np.cumsum(np.insert(values, 0, 0.0))
    out[period - 1 :] = (csum[period:] - csum[:-period]) / float(period)
    return out


def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    out = np.full(len(closes), np.nan, dtype=float)
    if len(closes) <= period:
        return out
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def _stoch_kd(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    n: int = 9,
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    if len(closes) < n + 2:
        return None, None, None, None
    k = 50.0
    d = 50.0
    prev_k, prev_d = k, d
    for i in range(n - 1, len(closes)):
        prev_k, prev_d = k, d
        hh = float(np.max(highs[i - n + 1 : i + 1]))
        ll = float(np.min(lows[i - n + 1 : i + 1]))
        rsv = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100.0
        k = (2.0 / 3.0) * k + (1.0 / 3.0) * rsv
        d = (2.0 / 3.0) * d + (1.0 / 3.0) * k
    return round(k, 1), round(d, 1), round(prev_k, 1), round(prev_d, 1)


def _r(val: Any, digits: int = 2) -> Optional[float]:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return round(float(val), digits)


def analyze_technicals(chart_data: Dict[str, Any]) -> TechnicalAnalysis:
    """根據日線 OHLCV 計算完整技術指標、綜合技術評分與優劣勢條列。"""
    bars: List[Dict[str, Any]] = chart_data.get("bars") or []
    closes = np.array([b["close"] for b in bars], dtype=float)
    highs = np.array([b["high"] for b in bars], dtype=float)
    lows = np.array([b["low"] for b in bars], dtype=float)
    vols = np.array([b["volume"] for b in bars], dtype=float)

    n = len(closes)
    price = float(closes[-1])

    def _chg(days: int) -> float:
        if n <= days:
            base = float(closes[0])
        else:
            base = float(closes[-1 - days])
        return round((price - base) / base * 100.0, 2) if base else 0.0

    c1d = _chg(1)
    c5d = _chg(5)
    c20d = _chg(20)
    c60d = _chg(60)

    ma5_arr = _sma(closes, 5)
    ma20_arr = _sma(closes, 20)
    ma60_arr = _sma(closes, 60)
    rsi_arr = _rsi(closes, 14)

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    macd_sig = _ema(macd_line, 9)
    macd_hist = macd_line - macd_sig

    # 布林通道 (20日 ± 2σ)
    bb_mid_val: Optional[float] = None
    bb_upper_val: Optional[float] = None
    bb_lower_val: Optional[float] = None
    if n >= 20:
        win = closes[-20:]
        bb_mid_val = float(np.mean(win))
        std20 = float(np.std(win))
        bb_upper_val = bb_mid_val + 2.0 * std20
        bb_lower_val = bb_mid_val - 2.0 * std20

    # KD 指標
    k_val, d_val, prev_k, prev_d = _stoch_kd(highs, lows, closes, 9)

    # 量能比 (當日量 / 近 20 日均量)
    vol_ratio: Optional[float] = None
    if n >= 20:
        avg_v = float(np.mean(vols[-20:]))
        if avg_v > 0 and vols[-1] > 0:
            vol_ratio = round(float(vols[-1]) / avg_v, 2)

    # ATR(14)% 波動度
    atr_pct: Optional[float] = None
    if n >= 15:
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
        )
        atr14 = float(np.mean(tr[-14:]))
        atr_pct = round(atr14 / price * 100.0, 2) if price > 0 else None

    # 支撐與壓力
    support = float(np.min(lows[-20:])) if n >= 20 else float(np.min(lows))
    resistance = float(np.max(highs[-20:])) if n >= 20 else float(np.max(highs))

    high_52w = chart_data.get("fifty_two_week_high") or float(np.max(highs))
    dist_52w = round((price - high_52w) / high_52w * 100.0, 2) if high_52w else None

    ma5 = _r(ma5_arr[-1])
    ma20 = _r(ma20_arr[-1])
    ma60 = _r(ma60_arr[-1])
    rsi14 = _r(rsi_arr[-1], 1)
    macd_v = _r(macd_line[-1], 3)
    macd_s = _r(macd_sig[-1], 3)
    macd_h = _r(macd_hist[-1], 3)
    prev_macd_h = _r(macd_hist[-2], 3) if n >= 2 else None

    # ---- 技術面評分與優劣勢自動判讀 ----
    score = 50.0
    pros: List[str] = []
    cons: List[str] = []

    # 1. 均線架構
    if ma5 and ma20 and ma60:
        if price > ma5 > ma20 > ma60:
            score += 18
            pros.append(f"均線呈標準多頭排列（現價 {price:.2f} > MA5 {ma5:.2f} > MA20 {ma20:.2f} > MA60 {ma60:.2f}），短中長線趨勢一致向上。")
        elif price > ma20 and price > ma60:
            score += 11
            pros.append(f"股價站穩月線（{ma20:.2f}）與季線（{ma60:.2f}）之上，中期結構維持偏多格局。")
        elif price < ma5 < ma20 < ma60:
            score -= 18
            cons.append(f"均線呈空頭排列（現價 {price:.2f} < MA5 < MA20 < MA60），上方均線層層反壓。")
        elif price < ma20 and price < ma60:
            score -= 11
            cons.append(f"股價失守月線（{ma20:.2f}）與季線（{ma60:.2f}），中期趨勢轉弱需防回測前低。")
        elif price > ma60 and price < ma20:
            score += 2
            pros.append(f"股價仍守住季線（{ma60:.2f}）長線支撐，短線回檔屬漲多整理。")
            cons.append(f"短線跌破月線（{ma20:.2f}），須觀察能否儘速站回化解修正壓力。")
        elif price > ma20 and price < ma60:
            score += 3
            pros.append(f"短線重新站上月線（{ma20:.2f}），具反彈修復契機。")
            cons.append(f"上方仍面臨季線（{ma60:.2f}）反壓，突破前宜留意解套賣壓。")

    # 2. MACD 動能
    if macd_h is not None and prev_macd_h is not None:
        if macd_h > 0 and macd_h >= prev_macd_h:
            score += 10
            pros.append(f"MACD 柱狀體位於零軸上方且持續放大（{macd_h:+.3f}），多方動能增強。")
        elif macd_h > 0 and prev_macd_h <= 0:
            score += 12
            pros.append("MACD 剛翻紅出現黃金交叉訊號，波段轉強訊號明確。")
        elif macd_h < 0 and prev_macd_h >= 0:
            score -= 11
            cons.append("MACD 剛翻黑形成死亡交叉，短線動能轉弱。")
        elif macd_h < 0 and macd_h < prev_macd_h:
            score -= 8
            cons.append(f"MACD 處於負值區且綠柱擴大（{macd_h:+.3f}），空方動能尚未收斂。")
        elif macd_h < 0 and macd_h > prev_macd_h:
            score += 3
            pros.append("MACD 負值柱狀體逐步收斂，跌勢動能放緩有築底跡象。")

    # 3. RSI(14) 強弱與過熱檢核
    if rsi14 is not None:
        if 52 <= rsi14 <= 68:
            score += 8
            pros.append(f"RSI(14) 位於 {rsi14:.1f} 健康強勢區，具備推升動能且尚未過熱。")
        elif rsi14 > 74:
            score += 2
            pros.append(f"RSI(14) 高達 {rsi14:.1f}，買盤追價動能極強。")
            cons.append(f"RSI(14) 已逾 74 進入短線超買區，須防高檔獲利了結震盪。")
        elif rsi14 < 30:
            score -= 4
            cons.append(f"RSI(14) 落至 {rsi14:.1f} 弱勢超賣區，市場賣壓偏重。")
            pros.append("短線乖離偏大進入技術性超賣區，具備醞釀反彈之潛力。")
        elif rsi14 < 45:
            score -= 6
            cons.append(f"RSI(14) 僅 {rsi14:.1f}，低於 50 多空分界線，買盤承接力道偏弱。")

    # 4. KD 與布林通道位置
    if k_val is not None and d_val is not None and prev_k is not None and prev_d is not None:
        if prev_k <= prev_d and k_val > d_val and k_val < 55:
            score += 7
            pros.append(f"日 KD 於中低檔黃金交叉（K={k_val:.1f} > D={d_val:.1f}），短線轉強訊號浮現。")
        elif prev_k >= prev_d and k_val < d_val and k_val > 70:
            score -= 6
            cons.append(f"日 KD 於高檔死亡交叉（K={k_val:.1f} < D={d_val:.1f}），留意短線回檔風險。")

    if bb_upper_val and bb_lower_val:
        if price >= bb_upper_val * 0.995:
            cons.append(f"股價逼近或突破布林上軌（{bb_upper_val:.2f}），短線正乖離偏大不宜過度追高。")
        elif price <= bb_lower_val * 1.01:
            cons.append(f"股價貼近布林下軌（{bb_lower_val:.2f}），短線走勢弱勢沿下軌承壓。")

    # 5. 量價關係與波動風險
    if vol_ratio is not None:
        if vol_ratio >= 1.35 and c1d > 0.8:
            score += 7
            pros.append(f"價漲量增（當日量能為 20 日均量之 {vol_ratio:.2f} 倍），法人或主力買盤進駐明顯。")
        elif vol_ratio >= 1.4 and c1d < -1.0:
            score -= 8
            cons.append(f"價跌量增（量比 {vol_ratio:.2f} 倍且單日下跌 {c1d:.2f}%），顯示高檔或停損賣壓湧現。")
        elif vol_ratio < 0.65:
            cons.append(f"量能明顯萎縮（量比僅 {vol_ratio:.2f} 倍），短線缺乏攻擊量能易呈盤整。")

    if atr_pct is not None and atr_pct >= 4.2:
        score -= 3
        cons.append(f"14 日真實波幅（ATR）達 {atr_pct:.2f}%，日內震盪劇烈，須嚴守停損紀律。")

    if dist_52w is not None and dist_52w <= -22.0:
        cons.append(f"距離 52 週高點仍回撤 {dist_52w:.1f}%，上方套牢籌碼較重。")
    elif dist_52w is not None and dist_52w >= -6.0:
        pros.append(f"股價逼近 52 週新高（僅差 {abs(dist_52w):.1f}%），上方籌碼阻力輕。")

    # 20 日動能加權微調
    score += max(-8.0, min(8.0, c20d * 0.35))
    final_score = round(max(5.0, min(98.0, score)), 1)

    if final_score >= 72:
        trend_label = "強勢多頭"
    elif final_score >= 58:
        trend_label = "溫和偏多"
    elif final_score >= 44:
        trend_label = "區間震盪"
    elif final_score >= 30:
        trend_label = "弱勢偏空"
    else:
        trend_label = "空頭排列"

    if not pros:
        pros.append(f"近期技術支撐參考位約 {support:.2f}，可作為防守觀察基準。")
    if not cons:
        cons.append(f"短線前高壓力參考位約 {resistance:.2f}，突破需搭配成交量放大確認。")

    # 輸出最近 65 個交易日序列供前端 Canvas K線／均線／RSI／MACD 繪圖
    tail = min(65, n)
    series: List[Dict[str, Any]] = []
    start_idx = n - tail
    for i in range(start_idx, n):
        b = bars[i]
        series.append(
            {
                "date": b["date"],
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "volume": b["volume"],
                "ma5": _r(ma5_arr[i]),
                "ma20": _r(ma20_arr[i]),
                "ma60": _r(ma60_arr[i]),
                "rsi14": _r(rsi_arr[i], 1),
                "macd_hist": _r(macd_hist[i], 3),
            }
        )

    return TechnicalAnalysis(
        score=final_score,
        trend_label=trend_label,
        price=round(price, 2),
        change_pct_1d=c1d,
        change_pct_5d=c5d,
        change_pct_20d=c20d,
        change_pct_60d=c60d,
        ma5=ma5,
        ma20=ma20,
        ma60=ma60,
        rsi14=rsi14,
        macd=macd_v,
        macd_signal=macd_s,
        macd_hist=macd_h,
        bb_upper=_r(bb_upper_val),
        bb_mid=_r(bb_mid_val),
        bb_lower=_r(bb_lower_val),
        k_val=k_val,
        d_val=d_val,
        volume_ratio=vol_ratio,
        atr_pct=atr_pct,
        support_level=round(support, 2),
        resistance_level=round(resistance, 2),
        distance_52w_high_pct=dist_52w,
        pros=pros[:5],
        cons=cons[:5],
        series=series,
    )
