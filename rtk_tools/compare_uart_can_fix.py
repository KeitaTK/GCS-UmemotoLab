#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_uart_can_fix.py — UART2(UBX-NAV-PVT) と CAN(DroneCAN Fix2) の fix 遷移を
同時監視し、遷移遅延・データ欠落率を比較するスクリプト。

【背景】
  - UART2監視: f9p_fix_monitor.py (F9P UART2 TX2 → UBX-NAV-PVT, 5Hz)
  - CAN監視:   can_fix_monitor.py   (AP_Periph → DroneCAN Fix2, 最大10Hz)

【動作】
  1. 両方の監視を並行実行し、タイムスタンプ付きで fix 状態を記録
  2. 遷移遅延（UART2 vs CAN の fix 変化タイミング差）を計測
  3. データ欠落率を比較
  4. 結果を CSV 出力（logs/uart_can_fix_comparison.csv）
  5. 比較レポートを自動生成して標準出力

【Fix 状態マッピング】
  UART2 carrSoln: 0=NONE, 1=FLOAT, 2=FIXED
  CAN mode:       0=SINGLE, 1=DGPS, 2=RTK_FLOAT, 3=RTK_FIXED
  共通スケール (normalized_fix):
    0 = NO_RTK   (UART2:0 / CAN:0,1)
    1 = FLOAT    (UART2:1 / CAN:2)
    2 = FIXED    (UART2:2 / CAN:3)

【使用例】
  python rtk_tools/compare_uart_can_fix.py
  python rtk_tools/compare_uart_can_fix.py --duration 180
  python rtk_tools/compare_uart_can_fix.py --uart-port /dev/ttyUSB0 --can-iface can0
  python rtk_tools/compare_uart_can_fix.py --csv-only
  python rtk_tools/compare_uart_can_fix.py --log-level DEBUG

【依存】
  - f9p_fix_monitor.F9pFixMonitor (import)
  - can_fix_monitor.CanFixMonitor  (import)
  - python-can                     (CanFixMonitor 経由)
"""

import argparse
import csv
import logging
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# 自身の rtk_tools ディレクトリを sys.path に追加
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from f9p_fix_monitor import F9pFixMonitor  # noqa: E402
from can_fix_monitor import CanFixMonitor   # noqa: E402

logger = logging.getLogger("compare_uart_can_fix")

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
UART_EXPECTED_HZ = 5.0       # UART2 UBX-NAV-PVT 想定レート
CAN_EXPECTED_HZ = 10.0       # CAN DroneCAN Fix2 想定レート

NORMALIZED_NAMES: dict[int, str] = {0: "NO_RTK", 1: "FLOAT", 2: "FIXED"}

CSV_OUTPUT_DIR = "logs"
CSV_OUTPUT_FILE = os.path.join(CSV_OUTPUT_DIR, "uart_can_fix_comparison.csv")


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------

@dataclass
class FixRecord:
    """1サンプルの fix 状態レコード"""
    source: str                  # "UART2" or "CAN"
    timestamp_mono: float        # time.monotonic() (高精度相対時刻)
    timestamp_iso: str           # ISO 8601 文字列 (UTC)
    normalized_fix: int          # 0=NO_RTK, 1=FLOAT, 2=FIXED
    raw_fix_value: int           # 生の値 (UART2: carrSoln, CAN: mode)
    raw_fix_name: str            # 人間可読名
    num_sv: int                  # 衛星数
    lat: float                   # 緯度 [deg]
    lon: float                   # 経度 [deg]
    h_msl: float                 # MSL高度 [m]
    h_acc: float | None = None   # 水平精度 [m] (UART2のみ)
    hdop: float | None = None    # HDOP (CANのみ)


@dataclass
class TransitionEvent:
    """Fix 遷移イベント（UART2 / CAN 間のタイミング差計測用）"""
    source: str                  # 先に遷移したソース
    normalized_fix_from: int
    normalized_fix_to: int
    time_uart2: float            # UART2 側で遷移が観測された monotonic 時刻
    time_can: float              # CAN 側で遷移が観測された monotonic 時刻
    delay_sec: float             # 遷移遅延 [秒] (CAN_time - UART2_time)


@dataclass
class ComparisonResult:
    """比較結果の集約"""
    duration_sec: float
    uart_records: int
    can_records: int
    uart_rate_hz: float
    can_rate_hz: float
    uart_loss_pct: float
    can_loss_pct: float
    transitions: list[TransitionEvent] = field(default_factory=list)
    final_uart_fix: int = -1
    final_can_fix: int = -1


# ---------------------------------------------------------------------------
# Fix 正規化
# ---------------------------------------------------------------------------

def normalize_uart_fix(carr_soln: int) -> int:
    """UART2 carrSoln → normalized_fix (0/1/2)"""
    if carr_soln in (0, 1, 2):
        return carr_soln
    logger.warning("Unexpected UART2 carrSoln=%d, mapping to 0", carr_soln)
    return 0


def normalize_can_fix(mode: int) -> int:
    """CAN mode → normalized_fix (0/1/2)"""
    if mode in (0, 1):          # SINGLE, DGPS → NO_RTK
        return 0
    elif mode == 2:              # RTK_FLOAT
        return 1
    elif mode == 3:              # RTK_FIXED
        return 2
    else:
        logger.warning("Unexpected CAN mode=%d, mapping to 0", mode)
        return 0



# ---------------------------------------------------------------------------
# UartCanFixComparator — 比較エンジン
# ---------------------------------------------------------------------------

class UartCanFixComparator:
    """UART2 と CAN の fix 状態を同時監視し比較する"""

    def __init__(
        self,
        uart_port: str = "/dev/ttyAMA4",
        uart_baud: int = 115200,
        can_interface: str = "can0",
        poll_interval: float = 0.2,
    ):
        self.uart_port = uart_port
        self.uart_baud = uart_baud
        self.can_interface = can_interface
        self.poll_interval = poll_interval
        self._uart_monitor: Optional[F9pFixMonitor] = None
        self._can_monitor: Optional[CanFixMonitor] = None
        self._running = False
        self._uart_thread: Optional[threading.Thread] = None
        self._can_thread: Optional[threading.Thread] = None
        self._record_queue: queue.Queue = queue.Queue()
        self._uart_records: list[FixRecord] = []
        self._can_records: list[FixRecord] = []
        self._prev_uart_norm: int = -1
        self._prev_can_norm: int = -1
        self._transitions: list[TransitionEvent] = []
        self._pending_uart: Optional[dict] = None
        self._pending_can: Optional[dict] = None

    def open(self) -> None:
        self._uart_monitor = F9pFixMonitor(
            serial_port=self.uart_port, baudrate=self.uart_baud)
        self._can_monitor = CanFixMonitor(interface=self.can_interface)
        self._uart_monitor.open()
        self._can_monitor.open()
        logger.info("Both monitors opened: UART2=%s @%d, CAN=%s",
                     self.uart_port, self.uart_baud, self.can_interface)

    def close(self) -> None:
        self._running = False
        if self._uart_thread and self._uart_thread.is_alive():
            self._uart_thread.join(timeout=5.0)
        if self._can_thread and self._can_thread.is_alive():
            self._can_thread.join(timeout=5.0)
        if self._uart_monitor:
            self._uart_monitor.close()
        if self._can_monitor:
            self._can_monitor.close()
        logger.info("Both monitors closed")


    # ------------------------------------------------------------------
    # ポーリングループ
    # ------------------------------------------------------------------

    def _uart_poll_loop(self) -> None:
        logger.info("UART2 poll loop started (interval=%.2fs)", self.poll_interval)
        while self._running:
            try:
                result = self._uart_monitor.poll_nav_pvt(timeout=1.0)
            except Exception as e:
                logger.error("UART2 poll error: %s", e)
                time.sleep(0.5)
                continue
            if result is not None:
                now_mono = time.monotonic()
                now_iso = datetime.now(timezone.utc).isoformat()
                norm = normalize_uart_fix(result["carrSoln"])
                rec = FixRecord(
                    source="UART2", timestamp_mono=now_mono,
                    timestamp_iso=now_iso, normalized_fix=norm,
                    raw_fix_value=result["carrSoln"],
                    raw_fix_name=result.get("carrSoln_name", "?"),
                    num_sv=result.get("numSV", 0),
                    lat=result.get("lat", 0.0), lon=result.get("lon", 0.0),
                    h_msl=result.get("hMSL", 0.0), h_acc=result.get("hAcc"),
                )
                self._record_queue.put(rec)
            time.sleep(self.poll_interval)
        logger.info("UART2 poll loop stopped")

    def _can_poll_loop(self) -> None:
        logger.info("CAN poll loop started (interval=%.2fs)", self.poll_interval)
        while self._running:
            try:
                result = self._can_monitor.receive_one(timeout=0.5)
            except Exception as e:
                logger.error("CAN poll error: %s", e)
                time.sleep(0.5)
                continue
            if result is not None:
                now_mono = time.monotonic()
                now_iso = datetime.now(timezone.utc).isoformat()
                norm = normalize_can_fix(result["mode"])
                rec = FixRecord(
                    source="CAN", timestamp_mono=now_mono,
                    timestamp_iso=now_iso, normalized_fix=norm,
                    raw_fix_value=result["mode"],
                    raw_fix_name=result.get("mode_name", "?"),
                    num_sv=result.get("sats_used", 0),
                    lat=result.get("lat", 0.0), lon=result.get("lon", 0.0),
                    h_msl=result.get("height_msl_m", 0.0),
                    hdop=result.get("hdop"),
                )
                self._record_queue.put(rec)
            time.sleep(self.poll_interval)
        logger.info("CAN poll loop stopped")

    # ------------------------------------------------------------------
    # 開始 / 停止
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._uart_thread = threading.Thread(
            target=self._uart_poll_loop, daemon=True, name="uart-poll")
        self._can_thread = threading.Thread(
            target=self._can_poll_loop, daemon=True, name="can-poll")
        self._uart_thread.start()
        self._can_thread.start()
        logger.info("Both poll threads started")

    def stop(self) -> None:
        self._running = False
        logger.info("Stop requested")

    # ------------------------------------------------------------------
    # レコード処理 + 遷移検出
    # ------------------------------------------------------------------

    def process_queue(self) -> None:
        """キュー内の全レコードを処理"""
        while not self._record_queue.empty():
            rec: FixRecord = self._record_queue.get_nowait()
            if rec.source == "UART2":
                self._process_uart_record(rec)
            else:
                self._process_can_record(rec)

    def _process_uart_record(self, rec: FixRecord) -> None:
        self._uart_records.append(rec)
        norm = rec.normalized_fix
        if self._prev_uart_norm != -1 and norm != self._prev_uart_norm:
            self._handle_transition(
                "UART2", self._prev_uart_norm, norm, rec.timestamp_mono)
        self._prev_uart_norm = norm

    def _process_can_record(self, rec: FixRecord) -> None:
        self._can_records.append(rec)
        norm = rec.normalized_fix
        if self._prev_can_norm != -1 and norm != self._prev_can_norm:
            self._handle_transition(
                "CAN", self._prev_can_norm, norm, rec.timestamp_mono)
        self._prev_can_norm = norm

    def _handle_transition(
        self, source: str, from_fix: int, to_fix: int, time_src: float
    ) -> None:
        """一方で遷移発生 → 反対側の保留中遷移とマッチング"""
        pending = self._pending_can if source == "UART2" else self._pending_uart

        if pending and pending["from"] == from_fix and pending["to"] == to_fix:
            # マッチ成立
            if source == "UART2":
                t_uart2, t_can = time_src, pending["time"]
            else:
                t_can, t_uart2 = time_src, pending["time"]
            first = "UART2" if t_uart2 <= t_can else "CAN"
            delay = t_can - t_uart2
            ev = TransitionEvent(
                source=first, normalized_fix_from=from_fix,
                normalized_fix_to=to_fix, time_uart2=t_uart2,
                time_can=t_can, delay_sec=delay)
            self._transitions.append(ev)
            if source == "UART2":
                self._pending_can = None
            else:
                self._pending_uart = None
            logger.info(
                "Transition matched: %d→%d | UART2=%.3f CAN=%.3f delay=%.3fs (1st=%s)",
                from_fix, to_fix, t_uart2, t_can, delay, first)
        else:
            entry = {"from": from_fix, "to": to_fix, "time": time_src}
            if source == "UART2":
                self._pending_uart = entry
            else:
                self._pending_can = entry
            logger.debug("Transition pending: %s %d→%d @%.3f",
                         source, from_fix, to_fix, time_src)


    # ------------------------------------------------------------------
    # 分析
    # ------------------------------------------------------------------

    def analyze(self, duration_sec: float) -> ComparisonResult:
        u_n = len(self._uart_records)
        c_n = len(self._can_records)
        u_rate = u_n / duration_sec if duration_sec > 0 else 0.0
        c_rate = c_n / duration_sec if duration_sec > 0 else 0.0
        u_loss = max(0.0, (1.0 - u_rate / UART_EXPECTED_HZ) * 100)
        c_loss = max(0.0, (1.0 - c_rate / CAN_EXPECTED_HZ) * 100)
        fu = self._uart_records[-1].normalized_fix if self._uart_records else -1
        fc = self._can_records[-1].normalized_fix if self._can_records else -1
        return ComparisonResult(
            duration_sec=duration_sec, uart_records=u_n, can_records=c_n,
            uart_rate_hz=u_rate, can_rate_hz=c_rate,
            uart_loss_pct=u_loss, can_loss_pct=c_loss,
            transitions=list(self._transitions),
            final_uart_fix=fu, final_can_fix=fc)

    # ------------------------------------------------------------------
    # CSV 出力
    # ------------------------------------------------------------------

    def write_csv(self, duration_sec: float) -> str:
        os.makedirs(CSV_OUTPUT_DIR, exist_ok=True)
        with open(CSV_OUTPUT_FILE, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "source", "timestamp_mono", "timestamp_iso",
                "normalized_fix", "raw_fix_value", "raw_fix_name",
                "num_sv", "lat", "lon", "h_msl", "h_acc", "hdop"])
            all_recs = sorted(
                self._uart_records + self._can_records,
                key=lambda r: r.timestamp_mono)
            for r in all_recs:
                w.writerow([
                    r.source, f"{r.timestamp_mono:.3f}", r.timestamp_iso,
                    r.normalized_fix, r.raw_fix_value, r.raw_fix_name,
                    r.num_sv, f"{r.lat:.7f}", f"{r.lon:.7f}",
                    f"{r.h_msl:.3f}",
                    f"{r.h_acc:.3f}" if r.h_acc is not None else "",
                    f"{r.hdop:.3f}" if r.hdop is not None else ""])
            # 遷移イベント
            if self._transitions:
                w.writerow([])
                w.writerow(["# TRANSITIONS", "first_source", "from", "to",
                            "time_uart2", "time_can", "delay_sec"])
                for ev in self._transitions:
                    w.writerow(["", ev.source, ev.normalized_fix_from,
                                ev.normalized_fix_to,
                                f"{ev.time_uart2:.3f}", f"{ev.time_can:.3f}",
                                f"{ev.delay_sec:.3f}"])
            # サマリ
            n_u = len(self._uart_records)
            n_c = len(self._can_records)
            w.writerow([])
            w.writerow(["# SUMMARY"])
            w.writerow(["duration_sec", f"{duration_sec:.1f}"])
            w.writerow(["uart_records", n_u])
            w.writerow(["can_records", n_c])
            w.writerow(["uart_rate_hz",
                        f"{n_u / duration_sec:.2f}" if duration_sec > 0 else "0"])
            w.writerow(["can_rate_hz",
                        f"{n_c / duration_sec:.2f}" if duration_sec > 0 else "0"])
        logger.info("CSV written: %s (%d records)", CSV_OUTPUT_FILE, len(all_recs))
        return CSV_OUTPUT_FILE

    @property
    def uart_records(self) -> list[FixRecord]:
        return self._uart_records

    @property
    def can_records(self) -> list[FixRecord]:
        return self._can_records



# ---------------------------------------------------------------------------
# レポート生成
# ---------------------------------------------------------------------------

def generate_report(result: ComparisonResult) -> str:
    """比較レポート文字列を生成"""
    lines: list[str] = []
    sep = "=" * 72
    lines.append(sep)
    lines.append("  UART2(UBX-NAV-PVT) vs CAN(DroneCAN Fix2) — Fix 遷移比較レポート")
    lines.append(sep)
    lines.append("")
    lines.append(f"  監視時間           : {result.duration_sec:.1f} 秒")
    lines.append(f"  UART2 受信数        : {result.uart_records} 件")
    lines.append(f"  CAN   受信数        : {result.can_records} 件")
    lines.append("")
    lines.append(f"  UART2 実効レート    : {result.uart_rate_hz:.2f} Hz  (期待 {UART_EXPECTED_HZ:.0f} Hz)")
    lines.append(f"  CAN   実効レート    : {result.can_rate_hz:.2f} Hz  (期待 {CAN_EXPECTED_HZ:.0f} Hz)")
    lines.append("")
    lines.append(f"  UART2 データ欠落率  : {result.uart_loss_pct:.1f} %")
    lines.append(f"  CAN   データ欠落率  : {result.can_loss_pct:.1f} %")
    lines.append("")
    lines.append(f"  最終 UART2 fix      : {NORMALIZED_NAMES.get(result.final_uart_fix, '?')}  (raw={result.final_uart_fix})")
    lines.append(f"  最終 CAN   fix      : {NORMALIZED_NAMES.get(result.final_can_fix, '?')}  (raw={result.final_can_fix})")
    lines.append("")

    # 遷移遅延
    if result.transitions:
        lines.append("-" * 72)
        lines.append("  Fix 遷移イベント一覧")
        lines.append("-" * 72)
        hdr = f"  {'#':>3}  {'遷移':>8}  {'先着':>6}  {'UART2時刻':>10}  {'CAN時刻':>10}  {'遅延[ms]':>10}  {'備考'}"
        lines.append(hdr)
        lines.append("  " + "-" * 67)
        delays_ms: list[float] = []
        for i, ev in enumerate(result.transitions, 1):
            frm = NORMALIZED_NAMES.get(ev.normalized_fix_from, "?")
            to = NORMALIZED_NAMES.get(ev.normalized_fix_to, "?")
            dms = ev.delay_sec * 1000
            delays_ms.append(abs(dms))
            if abs(ev.delay_sec) < 0.3:
                note = "同期 (良好)"
            elif abs(ev.delay_sec) < 1.0:
                note = "許容範囲内"
            else:
                note = "遅延大 (要確認)"
            lines.append(
                f"  {i:>3}  {frm:>4}→{to:<4}  {ev.source:>6}  "
                f"{ev.time_uart2:>10.3f}  {ev.time_can:>10.3f}  "
                f"{dms:>+9.1f}  {note}")
        lines.append("")
        if delays_ms:
            lines.append(f"  平均絶対遅延       : {sum(delays_ms)/len(delays_ms):.1f} ms")
            lines.append(f"  最大絶対遅延       : {max(delays_ms):.1f} ms")
            lines.append(f"  最小絶対遅延       : {min(delays_ms):.1f} ms")
    else:
        lines.append("  (遷移イベントなし — 監視中に fix 状態が変化しなかった)")
    lines.append("")

    # 判定
    lines.append("-" * 72)
    lines.append("  総合判定")
    lines.append("-" * 72)
    issues: list[str] = []
    if result.uart_loss_pct > 20:
        issues.append(f"UART2 欠落率高 ({result.uart_loss_pct:.0f}% > 20%)")
    if result.can_loss_pct > 20:
        issues.append(f"CAN 欠落率高 ({result.can_loss_pct:.0f}% > 20%)")
    if result.final_uart_fix != result.final_can_fix:
        issues.append(
            f"最終 fix 不一致 (UART2={NORMALIZED_NAMES.get(result.final_uart_fix,'?')}, "
            f"CAN={NORMALIZED_NAMES.get(result.final_can_fix,'?')})")
    for ev in result.transitions:
        if abs(ev.delay_sec) > 2.0:
            issues.append(f"遷移遅延 >2.0s ({ev.delay_sec*1000:.0f}ms)")
    if issues:
        lines.append("  ⚠ 問題検出:")
        for issue in issues:
            lines.append(f"    - {issue}")
    else:
        lines.append("  ✅ 問題なし — UART2 / CAN の fix 遷移は許容範囲内で一致")
    lines.append("")
    lines.append(sep)
    return "\n".join(lines)



# ---------------------------------------------------------------------------
# リアルタイム表示
# ---------------------------------------------------------------------------

def print_live_status(
    uart_rec: Optional[FixRecord], can_rec: Optional[FixRecord], elapsed: float
) -> None:
    """両方の最新状態を1行表示"""
    us = (f"UART2: {uart_rec.raw_fix_name:<6} SV={uart_rec.num_sv:>2}"
          if uart_rec else "UART2: (no data)           ")
    cs = (f"CAN:   {can_rec.raw_fix_name:<10} SV={can_rec.num_sv:>2}"
          if can_rec else "CAN:   (no data)              ")
    print(f"\r  t={elapsed:5.1f}s  |  {us}  |  {cs}", end="", flush=True)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="UART2(UBX-NAV-PVT) vs CAN(DroneCAN Fix2) Fix 遷移比較",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "使用例:\n"
            "  python rtk_tools/compare_uart_can_fix.py\n"
            "  python rtk_tools/compare_uart_can_fix.py --duration 180\n"
            "  python rtk_tools/compare_uart_can_fix.py --csv-only\n"
            "  python rtk_tools/compare_uart_can_fix.py --log-level DEBUG\n"
        ),
    )
    parser.add_argument("--uart-port", default="/dev/ttyAMA4",
                        help="UART2 シリアルポート (default: /dev/ttyAMA4)")
    parser.add_argument("--uart-baud", type=int, default=115200,
                        help="UART2 ボーレート (default: 115200)")
    parser.add_argument("--can-iface", default="can0",
                        help="CAN インターフェース名 (default: can0)")
    parser.add_argument("--duration", type=float, default=60.0,
                        help="監視時間 [秒] (default: 60)")
    parser.add_argument("--poll-interval", type=float, default=0.2,
                        help="各ソースのポーリング間隔 [秒] (default: 0.2)")
    parser.add_argument("--csv-only", action="store_true",
                        help="リアルタイム表示を省略し CSV/レポート出力のみ行う")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="ログレベル (default: INFO)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print(f"\n{'='*72}")
    print(f"  UART2 vs CAN Fix 遷移比較")
    print(f"  UART2 port   : {args.uart_port} @ {args.uart_baud}")
    print(f"  CAN iface    : {args.can_interface}")
    print(f"  Duration     : {args.duration:.0f}s")
    print(f"{'='*72}\n")

    comparator = UartCanFixComparator(
        uart_port=args.uart_port, uart_baud=args.uart_baud,
        can_interface=args.can_iface, poll_interval=args.poll_interval)

    try:
        comparator.open()
    except Exception as e:
        logger.error("Failed to open monitors: %s", e)
        print(f"\nERROR: モニタを開けませんでした: {e}")
        print("  - UART2: F9P が接続され UBX-NAV-PVT を出力しているか確認")
        print("  - CAN:   can0 が UP 状態か確認 (ip link show can0)")
        sys.exit(1)

    comparator.start()
    t_start = time.monotonic()
    last_print = t_start
    print_interval = 0.5
    latest_uart: Optional[FixRecord] = None
    latest_can: Optional[FixRecord] = None

    try:
        while time.monotonic() - t_start < args.duration:
            # キュー処理
            q = comparator._record_queue  # type: ignore[attr-defined]
            while not q.empty():
                rec: FixRecord = q.get_nowait()
                if rec.source == "UART2":
                    comparator._process_uart_record(rec)
                    latest_uart = rec
                else:
                    comparator._process_can_record(rec)
                    latest_can = rec
            # リアルタイム表示
            now = time.monotonic()
            if not args.csv_only and now - last_print >= print_interval:
                print_live_status(latest_uart, latest_can, now - t_start)
                last_print = now
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n\n中断されました (Ctrl+C)")
    finally:
        comparator.stop()
        elapsed_total = time.monotonic() - t_start
        # 残りキュー処理
        q = comparator._record_queue  # type: ignore[attr-defined]
        while not q.empty():
            rec = q.get_nowait()
            if rec.source == "UART2":
                comparator._process_uart_record(rec)
            else:
                comparator._process_can_record(rec)
        comparator.close()
        if not args.csv_only:
            print("")

    # 分析・出力
    result = comparator.analyze(elapsed_total)
    csv_path = comparator.write_csv(elapsed_total)
    report = generate_report(result)
    print(report)
    print(f"\n  CSV 出力: {csv_path}")
    print(f"  ログ出力: logs/ ディレクトリ\n")

    has_issues = (
        result.final_uart_fix != result.final_can_fix
        or result.uart_loss_pct > 50
        or result.can_loss_pct > 50
    )
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()

