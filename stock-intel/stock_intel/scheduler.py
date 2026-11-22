"""台美股盤前自動排程引擎（台北時間 Asia/Taipei，週一～週五自動執行分析與推播）。"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Set, Tuple
from zoneinfo import ZoneInfo

from stock_intel.analyzers.pipeline import StockIntelPipeline
from stock_intel.config import OUTPUT_DIR
from stock_intel.notifications.notifier import dispatch_notifications
from stock_intel.web.report_exporter import export_markdown_report, export_standalone_html

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def _parse_hhmm(raw: str, default: Tuple[int, int]) -> Tuple[int, int]:
    try:
        h, m = raw.strip().split(":")
        return int(h), int(m)
    except Exception:
        return default


def execute_session(session: str = "tw_premarket", dry_run: bool = False) -> dict:
    """執行單次盤前完整任務：全球新聞 -> 三大法人 -> 策略回測 -> 匯出報告 -> 推播通知。"""
    now_tpe = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"\n[{now_tpe}] 開始執行盤前任務：{session}")

    pipeline = StockIntelPipeline()
    report = pipeline.run_full_analysis(save_to_db=True)
    report_dict = report.to_dict()

    export_markdown_report(report_dict, OUTPUT_DIR / "latest_report.md")
    export_standalone_html(report_dict, OUTPUT_DIR / "latest_dashboard.html")
    export_markdown_report(report_dict, OUTPUT_DIR / f"{session}_latest.md")

    push_res = dispatch_notifications(report_dict, session=session, dry_run=dry_run)
    print(f"[{session}] 推播結果：{push_res['results']}")
    return push_res


def run_scheduler_loop(dry_run: bool = False) -> None:
    """常駐排程主迴圈：每個交易日（週一至週五）台北時間台股盤前與美股盤前各自動執行一次。"""
    tw_h, tw_m = _parse_hhmm(os.getenv("TW_PREMARKET_TIME", "08:15"), (8, 15))
    us_h, us_m = _parse_hhmm(os.getenv("US_PREMARKET_TIME", "20:45"), (20, 45))

    print("=" * 68)
    print("  Stock Intel 台美股盤前自動排程器已啟動 (時區: Asia/Taipei)")
    print(f"  • 台股盤前場次：週一～週五 {tw_h:02d}:{tw_m:02d}")
    print(f"  • 美股盤前場次：週一～週五 {us_h:02d}:{us_m:02d}")
    print(f"  • 模式：{'Dry-Run 預覽' if dry_run else '正式多管道推播'}")
    print("  按 Ctrl+C 可安全結束排程。")
    print("=" * 68)

    executed_keys: Set[str] = set()
    while True:
        now = datetime.now(TAIPEI_TZ)
        # 週一(0) ~ 週五(4) 執行
        if now.weekday() < 5:
            day_str = now.strftime("%Y-%m-%d")
            schedule_slots = [
                ("tw_premarket", tw_h, tw_m),
                ("us_premarket", us_h, us_m),
            ]
            for sess, hh, mm in schedule_slots:
                key = f"{day_str}:{sess}"
                if key not in executed_keys and now.hour == hh and now.minute == mm:
                    executed_keys.add(key)
                    try:
                        execute_session(session=sess, dry_run=dry_run)
                    except Exception as exc:
                        print(f"[排程錯誤] {sess} 執行失敗：{exc}")
        time.sleep(20)
