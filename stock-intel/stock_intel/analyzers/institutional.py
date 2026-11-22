"""台股三大法人籌碼分析引擎（外資、投信、自營商大盤金額與個股張數評分及優劣勢判讀）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from stock_intel.models import TWMarketInstitutional, TWStockInstitutional


def analyze_tw_market_institutional(raw: Optional[Dict[str, Any]]) -> Optional[TWMarketInstitutional]:
    """解析 TWSE BFI82U 大盤三大法人買賣超（億元），產出籌碼多空訊號。"""
    if not raw or not raw.get("date"):
        return None

    f_b = round(float(raw.get("foreign_net_billion", 0.0)), 2)
    t_b = round(float(raw.get("trust_net_billion", 0.0)), 2)
    d_b = round(float(raw.get("dealer_net_billion", 0.0)), 2)
    tot_b = round(float(raw.get("total_net_billion", 0.0)), 2)

    if tot_b >= 200:
        signal = "法人大買"
    elif tot_b >= 40:
        signal = "溫和買超"
    elif tot_b <= -200:
        signal = "法人大賣"
    elif tot_b <= -40:
        signal = "溫和賣超"
    else:
        signal = "籌碼分歧"

    if f_b > 0 and t_b > 0:
        align = "外資與投信同步偏多買超（土洋合擊）"
    elif f_b < 0 and t_b < 0:
        align = "外資與投信同步站賣方（籌碼承壓）"
    elif f_b < 0 and t_b > 0:
        align = "外資提款但投信逆勢護盤承接（土洋對作）"
    else:
        align = "外資回補而內資調節（土洋分歧）"

    summary = (
        f"台股 {raw['date']} 三大法人合計 {tot_b:+.2f} 億元"
        f"（外資 {f_b:+.2f} 億、投信 {t_b:+.2f} 億、自營商 {d_b:+.2f} 億），呈現「{align}」。"
    )
    return TWMarketInstitutional(
        date=str(raw["date"]),
        foreign_net_billion=f_b,
        trust_net_billion=t_b,
        dealer_net_billion=d_b,
        total_net_billion=tot_b,
        signal=signal,
        summary=summary,
    )


def analyze_tw_stock_institutional(raw: Optional[Dict[str, Any]]) -> Optional[TWStockInstitutional]:
    """解析 TWSE T86 個股三大法人買賣超張數，產出籌碼面評分 (0~100) 與優劣勢條列。"""
    if not raw or not raw.get("date"):
        return None

    f_lots = int(raw.get("foreign_net_lots", 0))
    t_lots = int(raw.get("trust_net_lots", 0))
    d_lots = int(raw.get("dealer_net_lots", 0))
    tot_lots = int(raw.get("total_net_lots", 0))

    score = 50.0
    pros: List[str] = []
    cons: List[str] = []

    # 1. 外資動向（權值股主導力量）
    if f_lots >= 2000:
        score += 18
        pros.append(f"外資大舉買超 {f_lots:+,d} 張，國際資金買盤動能強勁。")
    elif f_lots >= 300:
        score += 9
        pros.append(f"外資站在買方（買超 {f_lots:+,d} 張），籌碼面具正向支撐。")
    elif f_lots <= -2000:
        score -= 18
        cons.append(f"外資大舉提款賣超 {f_lots:+,d} 張，短線籌碼賣壓沉重。")
    elif f_lots <= -300:
        score -= 9
        cons.append(f"外資偏向調節（賣超 {f_lots:+,d} 張），須留意續賣壓力。")

    # 2. 投信動向（台灣內資波段認養指標）
    if t_lots >= 500:
        score += 14
        pros.append(f"投信明顯加碼 {t_lots:+,d} 張，具備內資認養與作帳題材。")
    elif t_lots >= 50:
        score += 7
        pros.append(f"投信小幅買超 {t_lots:+,d} 張，內資逢低承接意願佳。")
    elif t_lots <= -500:
        score -= 13
        cons.append(f"投信大幅結帳賣超 {t_lots:+,d} 張，須防內資停損或換股賣壓。")
    elif t_lots <= -50:
        score -= 6
        cons.append(f"投信微幅調節 {t_lots:+,d} 張。")

    # 3. 土洋同向共振加權
    if f_lots > 200 and t_lots > 50:
        score += 10
        signal = "土洋合擊買超"
        pros.append("外資與投信同步買超（土洋合擊），籌碼集中度顯著提升。")
    elif f_lots < -200 and t_lots < -50:
        score -= 10
        signal = "土洋同步賣超"
        cons.append("外資與投信同步站賣方，短線缺乏法人護盤力道。")
    elif f_lots >= 300:
        signal = "外資主導買超"
    elif t_lots >= 100 and f_lots < 0:
        signal = "投信逆勢護盤"
        pros.append(f"外資賣超之際投信逆勢承接 {t_lots:+,d} 張，下檔具內資支撐。")
    elif tot_lots <= -500:
        signal = "法人調節賣超"
    elif tot_lots >= 500:
        signal = "法人溫和買超"
    else:
        signal = "籌碼中性"

    # 自營商動向
    if abs(d_lots) >= 500:
        if d_lots > 0:
            score += 4
            pros.append(f"自營商買超 {d_lots:+,d} 張（含避險部位回補）。")
        else:
            score -= 4
            cons.append(f"自營商賣超 {d_lots:+,d} 張，留意權證避險賣壓。")

    final_score = round(max(5.0, min(96.0, score)), 1)
    if not pros:
        pros.append(f"最新交易日（{raw['date']}）三大法人籌碼未見明顯異常大買，持續追蹤連續買超天數。")
    if not cons:
        cons.append(f"三大法人合計 {tot_lots:+,d} 張，仍須留意隔日外資受美股波動之換手節奏。")

    return TWStockInstitutional(
        date=str(raw["date"]),
        foreign_net_lots=f_lots,
        trust_net_lots=t_lots,
        dealer_net_lots=d_lots,
        total_net_lots=tot_lots,
        score=final_score,
        signal=signal,
        pros=pros[:4],
        cons=cons[:4],
    )
