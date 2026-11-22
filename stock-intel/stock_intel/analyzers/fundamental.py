"""基本面量化評分引擎：估值、獲利能力、營收成長（含台股月營收）、財務健康度與優劣勢分析。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from stock_intel.models import FundamentalAnalysis


def analyze_fundamentals(
    raw: Dict[str, Any],
    current_price: float,
    market: str = "US",
) -> FundamentalAnalysis:
    """根據 Yahoo quoteSummary 與 TWSE 官方財報數據計算基本面評分、評級與優劣勢條列。"""
    pe = raw.get("pe_ratio")
    fwd_pe = raw.get("forward_pe")
    pb = raw.get("pb_ratio")
    div_y = raw.get("dividend_yield_pct")
    roe = raw.get("roe_pct")
    gm = raw.get("gross_margin_pct")
    om = raw.get("operating_margin_pct")
    pm = raw.get("profit_margin_pct")
    rev_g = raw.get("revenue_growth_pct")
    earn_g = raw.get("earnings_growth_pct")
    dte = raw.get("debt_to_equity")
    cr = raw.get("current_ratio")
    fcf = raw.get("free_cash_flow")
    target = raw.get("target_mean_price")
    consensus = raw.get("analyst_consensus")
    tw_rev_yoy = raw.get("twse_monthly_rev_yoy_pct")
    tw_rev_mom = raw.get("twse_monthly_rev_mom_pct")
    tw_cum_yoy = raw.get("twse_cum_rev_yoy_pct")
    tw_period = raw.get("twse_rev_period")

    target_upside: Optional[float] = None
    if target and current_price > 0:
        target_upside = round((target - current_price) / current_price * 100.0, 2)

    score = 46.0
    pros: List[str] = []
    cons: List[str] = []

    # 1. 估值水準（PE / Forward PE / PB）
    eff_pe = fwd_pe if (fwd_pe and fwd_pe > 0) else pe
    if pe is not None:
        if pe <= 0:
            score -= 10
            cons.append(f"目前本益比為負值或虧損狀態（PE {pe:.1f}），基本面尚未實現穩定獲利。")
        elif eff_pe and eff_pe <= 16:
            score += 9
            pros.append(f"估值具吸引力（本益比 {pe:.1f} 倍" + (f"、預估本益比 {fwd_pe:.1f} 倍" if fwd_pe else "") + "），具安全邊際。")
        elif eff_pe and eff_pe <= 28:
            score += 5
            pros.append(f"本益比處於合理成長區間（PE {pe:.1f} 倍" + (f" / 預估 {fwd_pe:.1f} 倍" if fwd_pe else "") + "）。")
        elif eff_pe and eff_pe >= 45:
            score -= 8
            cons.append(f"本益比高達 {pe:.1f} 倍（預估 {fwd_pe:.1f} 倍），估值偏貴，對成長不如預期的容忍度低。" if fwd_pe else f"本益比高達 {pe:.1f} 倍，估值明顯偏高，須嚴防估值修正風險。")
        elif eff_pe and eff_pe >= 32:
            score -= 3
            cons.append(f"本益比 {pe:.1f} 倍略高於大盤均值，須依靠高獲利成長來消化估值。")

    if pb is not None and pb >= 6.0:
        score -= 2
        cons.append(f"股價淨值比達 {pb:.2f} 倍，帳面溢價較高，大盤修正期容易伴隨估值回調。")
    elif pb is not None and 0 < pb <= 1.3:
        score += 3
        pros.append(f"股價淨值比僅 {pb:.2f} 倍，具備資產價值保護。")

    if pe and fwd_pe and pe > 0 and fwd_pe > 0 and fwd_pe < pe * 0.85:
        score += 4
        pros.append(f"預估本益比（{fwd_pe:.1f}x）明顯低於歷史本益比（{pe:.1f}x），反映市場預期未來獲利持續擴張。")

    # 2. 獲利能力（ROE / 毛利率 / 營益率 / 淨利率）
    if roe is not None:
        if roe >= 22:
            score += 10
            pros.append(f"股東權益報酬率（ROE）高達 {roe:.1f}%，資本運用效率與護城河極佳。")
        elif roe >= 12:
            score += 6
            pros.append(f"ROE 達 {roe:.1f}%，具備穩健的股東回報能力。")
        elif roe < 6:
            score -= 7
            cons.append(f"ROE 僅 {roe:.1f}%，資本回報效率偏低，競爭優勢不明顯。")

    if gm is not None:
        if gm >= 50:
            score += 6
            pros.append(f"毛利率高達 {gm:.1f}%，顯示產品具高度定價權與技術壁壘。")
        elif gm < 15:
            score -= 4
            cons.append(f"毛利率僅 {gm:.1f}%，屬偏低毛利結構，易受原物料或代工價格波動壓縮。")

    if pm is not None:
        if pm >= 20:
            score += 4
        elif pm < 4:
            score -= 5
            cons.append(f"稅後淨利率僅 {pm:.1f}%，最終獲利緩衝空間較薄。")

    # 3. 成長動能（財報營收成長 + 台股最新月營收）
    best_rev_g = tw_rev_yoy if (market == "TW" and tw_rev_yoy is not None) else rev_g
    if market == "TW" and tw_rev_yoy is not None:
        period_lbl = f"（{tw_period}）" if tw_period else ""
        if tw_rev_yoy >= 20:
            score += 10
            pros.append(
                f"TWSE 最新月營收{period_lbl}年增 {tw_rev_yoy:+.1f}%"
                + (f"（累計年增 {tw_cum_yoy:+.1f}%）" if tw_cum_yoy is not None else "")
                + "，營運動能爆發強勁。"
            )
        elif tw_rev_yoy >= 5:
            score += 5
            pros.append(f"TWSE 最新月營收{period_lbl}年增 {tw_rev_yoy:+.1f}%，營運維持穩健擴張。")
        elif tw_rev_yoy <= -10:
            score -= 9
            cons.append(f"TWSE 最新月營收{period_lbl}年減 {tw_rev_yoy:+.1f}%，營運面臨衰退逆風。")
        elif tw_rev_yoy < 0:
            score -= 4
            cons.append(f"TWSE 最新月營收{period_lbl}微幅年減 {tw_rev_yoy:+.1f}%，成長動能暫緩。")
    elif best_rev_g is not None:
        if best_rev_g >= 20:
            score += 9
            pros.append(f"季度營收年增高達 {best_rev_g:+.1f}%，處於高速成長軌道。")
        elif best_rev_g >= 7:
            score += 5
            pros.append(f"季度營收維持 {best_rev_g:+.1f}% 穩健年成長。")
        elif best_rev_g < 0:
            score -= 8
            cons.append(f"近期營收年增轉負（{best_rev_g:+.1f}%），需求動能出現放緩。")

    if earn_g is not None:
        if earn_g >= 20:
            score += 5
            pros.append(f"獲利年增率達 {earn_g:+.1f}%，營運槓桿效益顯著。")
        elif earn_g <= -15:
            score -= 6
            cons.append(f"盈餘年減 {earn_g:+.1f}%，獲利能力面臨短期修正。")

    # 4. 股利殖利率（對台股與金融/能源防禦股尤其重要）
    if div_y is not None:
        if div_y >= 4.0:
            score += 6
            pros.append(f"現金殖利率達 {div_y:.2f}%，具下檔防禦保護與配息吸引力。")
        elif div_y >= 2.2:
            score += 3
        elif market == "TW" and div_y < 1.5:
            cons.append(f"現金殖利率僅 {div_y:.2f}%，偏向成長型配置，息收防禦保護相對有限。")

    # 5. 財務結構與現金流
    if dte is not None:
        # Yahoo 的 debtToEquity 通常以百分比表示 (如 120 = 120%)
        if dte > 180:
            score -= 6
            cons.append(f"負債權益比偏高（{dte:.1f}%），高利率環境下利息負擔與財務槓桿較高。")
        elif dte < 50:
            score += 4
            pros.append(f"負債權益比僅 {dte:.1f}%，資產負債表結構穩健、抗風險能力強。")

    if fcf is not None:
        if fcf < 0:
            score -= 5
            cons.append("自由現金流呈現負值，須留意資本支出回收與籌資壓力。")
        elif fcf > 0:
            score += 3

    # 6. 華爾街／法人目標價共識空間
    if target_upside is not None:
        if target_upside >= 15:
            score += 5
            pros.append(f"法人平均目標價 {target:.2f}（潛在上漲空間 {target_upside:+.1f}%），市場共識偏多。")
        elif target_upside <= -8:
            score -= 5
            cons.append(f"現價已高於法人平均目標價 {target:.2f}（空間 {target_upside:+.1f}%），短線溢價偏高。")

    final_score = round(max(10.0, min(96.0, score)), 1)
    if final_score >= 82:
        grade = "A+"
    elif final_score >= 72:
        grade = "A"
    elif final_score >= 62:
        grade = "B+"
    elif final_score >= 52:
        grade = "B"
    elif final_score >= 42:
        grade = "C"
    else:
        grade = "D"

    if not pros:
        pros.append("具備產業代表地位，建議搭配法說會展望與財報更新追蹤。")
    if not cons:
        cons.append("需持續追蹤原物料成本、匯率波動與同業競爭對毛利率之影響。")

    return FundamentalAnalysis(
        score=final_score,
        grade=grade,
        market_cap=raw.get("market_cap"),
        currency=raw.get("currency", "TWD" if market == "TW" else "USD"),
        pe_ratio=round(pe, 2) if pe is not None else None,
        forward_pe=round(fwd_pe, 2) if fwd_pe is not None else None,
        pb_ratio=round(pb, 2) if pb is not None else None,
        dividend_yield_pct=round(div_y, 2) if div_y is not None else None,
        roe_pct=roe,
        gross_margin_pct=gm,
        operating_margin_pct=om,
        profit_margin_pct=pm,
        revenue_growth_pct=rev_g,
        earnings_growth_pct=earn_g,
        debt_to_equity=round(dte, 1) if dte is not None else None,
        current_ratio=round(cr, 2) if cr is not None else None,
        free_cash_flow=fcf,
        target_mean_price=round(target, 2) if target is not None else None,
        target_upside_pct=target_upside,
        analyst_consensus=consensus,
        twse_monthly_rev_yoy_pct=tw_rev_yoy,
        twse_monthly_rev_mom_pct=tw_rev_mom,
        twse_cum_rev_yoy_pct=tw_cum_yoy,
        twse_rev_period=tw_period,
        data_source=raw.get("data_source", "yahoo"),
        pros=pros[:5],
        cons=cons[:5],
    )
