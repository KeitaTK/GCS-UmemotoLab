#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
can_fix_monitor.py — DroneCAN Fix2 を CAN 経由で受信・表示

AP_Periph (STM32) が CAN バスに流す DroneCAN gnss.Fix2 メッセージを
Raspberry Pi 上で python-can (SocketCAN) を使って直接受信し、
Fix 状態・衛星数・位置・DOP 等をリアルタイムでログ出力する。

前提:
  - CAN I/F 設定 (deploy/can_setup_raspi.sh) が完了
  - AP_Periph CAN_GNSS_FIX2_RATE が有効 (例: 10Hz)
  - python-can がインストール済み ($ pip install python-can)

DroneCAN メッセージ構造 (uavcan.equipment.gnss.Fix2):
  uint64  timestamp / gnss_timestamp  (µs)
  uint8   num_leap_seconds (deprecated)
  int64   longitude_deg / latitude_deg (1e-8 deg)
  int32   height_ellipsoid_mm / height_msl_mm
  float32[3] ned_velocity (m/s)
  uint8   sats_used
  uint8   status (0=NO_FIX, 1=TIME_ONLY, 2=2D_FIX, 3=3D_FIX, 4=DGPS)
  uint8   mode   (0=SINGLE, 1=DGPS, 2=RTK_FLOAT, 3=RTK_FIXED, 4=PPP)
  uint8   sub_mode
  float16[<=36] covariance
  float16 pdop/hdop/vdop/tdop/ndop/edop

CAN ID フィルタリング:
  Fix2 Subject ID = 1063 (0x427)
  29-bit CAN ID = Priority(3) | 0(1) | SubjectID(17) | SourceNode(7)
  フィルタ: can_id=0x042700, can_mask=0x1FFF00

使用例:
  python rtk_tools/can_fix_monitor.py --once
  python rtk_tools/can_fix_monitor.py --monitor
  python rtk_tools/can_fix_monitor.py --monitor --log-level DEBUG

参考:
  deploy/can_setup_raspi.sh : CAN I/F 設定
  rtk_tools/f9p_fix_monitor.py : UART 経由 F9P モニタ (類似実装)
"""

import argparse
import logging
import struct
import sys
import time
from typing import Callable, Optional, Tuple

try:
    import can
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False

logger = logging.getLogger("can_fix_monitor")

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
FIX2_SUBJECT_ID = 1063  # 0x427 (uavcan.equipment.gnss.Fix2)
SUBJECT_ID_SHIFT = 8
SUBJECT_ID_MASK = 0x1FFF
CAN_FILTER_ID = (FIX2_SUBJECT_ID << SUBJECT_ID_SHIFT) & 0x1FFFFFFF
CAN_FILTER_MASK = SUBJECT_ID_MASK << SUBJECT_ID_SHIFT

STATUS_NAMES: dict[int, str] = {
    0: "NO_FIX", 1: "TIME_ONLY", 2: "2D_FIX", 3: "3D_FIX", 4: "DGPS",
}
MODE_NAMES: dict[int, str] = {
    0: "SINGLE", 1: "DGPS", 2: "RTK_FLOAT", 3: "RTK_FIXED", 4: "PPP",
}

# DSDL レイアウト (リトルエンディアン, パディングなし)
#   QQ     : uint64 x2                         = 16 bytes
#   B      : uint8                              =  1 byte
#   qq     : int64 x2 (lon_deg_e8, lat_deg_e8)  = 16 bytes
#   ii     : int32 x2 (height_ellip, height_msl)=  8 bytes
#   fff    : float32[3] (ned_velocity)           = 12 bytes
#   BBBB   : uint8 x4 (sats,status,mode,sub)     =  4 bytes
FIX2_HEADER_FMT = "<QQBqqiifffBBBB"
FIX2_HEADER_SIZE = struct.calcsize(FIX2_HEADER_FMT)  # 57

# DOP: covariance の後ろ 6 個の float16
FIX2_DOP_FMT = "<eeeeee"
FIX2_DOP_SIZE = struct.calcsize(FIX2_DOP_FMT)  # 12

FIX2_MIN_SIZE = FIX2_HEADER_SIZE + 1 + FIX2_DOP_SIZE  # 70
FIX2_COV_MAX = 36

# ---------------------------------------------------------------------------
# CAN トランスポート層: マルチフレーム再構築
# ---------------------------------------------------------------------------

class CanTransportReassembler:
    """UAVCAN CAN バス・トランスポート層のマルチフレーム再構築。

    テイルバイト (末尾 1 byte):
      bit 7   : 0=シングル, 1=マルチ
      bit 6   : 0=転送開始, 1=転送継続
      bit 5   : トグルビット (交互反転)
      bit 4-0 : 転送ID (0-31)
    """
    TRANSFER_TIMEOUT = 2.0

    def __init__(self):
        self._buffers: dict[Tuple[int, int], dict] = {}

    def feed(self, can_frame: "can.Message") -> list[bytes]:
        payload = can_frame.data
        if len(payload) < 1:
            return []

        tail_byte = payload[-1]
        data_bytes = payload[:-1]
        is_multi = (tail_byte & 0x80) != 0

        if not is_multi:
            return [bytes(data_bytes)]

        is_start = (tail_byte & 0x40) == 0
        toggle = (tail_byte >> 5) & 1
        transfer_id = tail_byte & 0x1F
        source_node = can_frame.arbitration_id & 0x7F
        key = (source_node, transfer_id)
        now = time.monotonic()

        self._gc_expired(now)

        if is_start:
            self._buffers[key] = {"data": bytearray(data_bytes), "toggle": toggle, "ts": now}
            return []

        existing = self._buffers.get(key)
        if existing is None:
            logger.debug("Orphan frame: src=%d tid=%d", source_node, transfer_id)
            return []

        existing["data"].extend(data_bytes)
        existing["toggle"] = toggle
        existing["ts"] = now

        if len(can_frame.data) < 8:  # DLC<8 → 最終フレーム
            completed = bytes(existing["data"])
            del self._buffers[key]
            logger.debug("Transfer done: src=%d tid=%d size=%d", source_node, transfer_id, len(completed))
            return [completed]
        return []

    def _gc_expired(self, now: float) -> None:
        expired = [k for k, v in self._buffers.items() if now - v["ts"] > self.TRANSFER_TIMEOUT]
        for k in expired:
            logger.debug("Transfer timeout: src=%d tid=%d", k[0], k[1])
            del self._buffers[k]

    def reset(self) -> None:
        self._buffers.clear()


# ---------------------------------------------------------------------------
# Fix2 パーサ
# ---------------------------------------------------------------------------

def parse_fix2(payload: bytes) -> Optional[dict]:
    """DroneCAN Fix2 DSDL ペイロード → dict"""
    if len(payload) < FIX2_MIN_SIZE:
        logger.debug("Payload too short: %d < %d", len(payload), FIX2_MIN_SIZE)
        return None

    try:
        h = struct.unpack_from(FIX2_HEADER_FMT, payload, 0)
        (ts, gnss_ts, _nls, lon_e8, lat_e8, h_ellip_mm, h_msl_mm,
         vn, ve, vd, sats, status, mode, sub_mode) = h

        cov_off = FIX2_HEADER_SIZE
        cov_len = min(payload[cov_off], FIX2_COV_MAX)
        dop_off = cov_off + 1 + cov_len * 2
        if dop_off + FIX2_DOP_SIZE > len(payload):
            logger.debug("Payload truncated at DOP")
            return None

        dops = struct.unpack_from(FIX2_DOP_FMT, payload, dop_off)

        return {
            "timestamp_us": ts,
            "gnss_timestamp_us": gnss_ts,
            "lat": lat_e8 * 1e-8,
            "lon": lon_e8 * 1e-8,
            "height_msl_m": h_msl_mm * 0.001,
            "height_ellipsoid_m": h_ellip_mm * 0.001,
            "ned_velocity_ms": (vn, ve, vd),
            "sats_used": sats,
            "status": status,
            "status_name": STATUS_NAMES.get(status, f"UNK({status})"),
            "mode": mode,
            "mode_name": MODE_NAMES.get(mode, f"UNK({mode})"),
            "sub_mode": sub_mode,
            "pdop": float(dops[0]), "hdop": float(dops[1]), "vdop": float(dops[2]),
            "tdop": float(dops[3]), "ndop": float(dops[4]), "edop": float(dops[5]),
        }
    except (struct.error, IndexError) as e:
        logger.debug("Parse error: %s", e)
        return None


# ---------------------------------------------------------------------------
# 表示フォーマット
# ---------------------------------------------------------------------------

HEADER_LINE = (
    f"{'elapsed':>7}  {'mode':<10}  {'status':<9}  {'sats':>3}  "
    f"{'lat':>12}  {'lon':>12}  {'hMSL':>8}  {'hdop':>5}  {'vdop':>5}"
)

FMT = (
    "{elapsed:>7.1f}s  mode={mode:<10s}  status={status:<9s}  sats={sats_used:>3d}  "
    "lat={lat:>12.7f}  lon={lon:>12.7f}  hMSL={hmsl:>8.2f}m  hdop={hdop:>5.1f}  vdop={vdop:>5.1f}"
)


def format_fix2(result: dict, elapsed: float = 0.0) -> str:
    return FMT.format(
        elapsed=elapsed, mode=result.get("mode_name", "?"),
        status=result.get("status_name", "?"), sats_used=result.get("sats_used", 0),
        lat=result.get("lat", 0.0), lon=result.get("lon", 0.0),
        hmsl=result.get("height_msl_m", 0.0),
        hdop=result.get("hdop", 99.9), vdop=result.get("vdop", 99.9),
    )


def format_fix2_verbose(result: dict) -> str:
    vel = result.get("ned_velocity_ms", (0, 0, 0))
    return (
        f"mode={result.get('mode_name','?')}  status={result.get('status_name','?')}  sub={result.get('sub_mode',0)}\n"
        f"  sats_used={result.get('sats_used',0)}\n"
        f"  lat={result.get('lat',0):.7f}  lon={result.get('lon',0):.7f}\n"
        f"  hMSL={result.get('height_msl_m',0):.3f}m  hEllip={result.get('height_ellipsoid_m',0):.3f}m\n"
        f"  vel NED=({vel[0]:.3f},{vel[1]:.3f},{vel[2]:.3f}) m/s\n"
        f"  pdop={result.get('pdop',0):.1f} hdop={result.get('hdop',0):.1f} vdop={result.get('vdop',0):.1f}\n"
        f"  tdop={result.get('tdop',0):.1f} ndop={result.get('ndop',0):.1f} edop={result.get('edop',0):.1f}\n"
        f"  ts={result.get('timestamp_us',0)} gnss_ts={result.get('gnss_timestamp_us',0)}"
    )


# ---------------------------------------------------------------------------
# CanFixMonitor
# ---------------------------------------------------------------------------

class CanFixMonitor:
    """CAN インターフェースから DroneCAN Fix2 メッセージを受信・監視"""

    def __init__(self, interface: str = "can0", timeout: float = 1.0):
        if not CAN_AVAILABLE:
            raise ImportError("python-can not installed. Run: pip install python-can")
        self.interface = interface
        self.timeout = timeout
        self._bus: Optional["can.BusABC"] = None
        self._reasm = CanTransportReassembler()
        self._running = False
        self.stats = {"can_frames": 0, "fix2_messages": 0, "parse_errors": 0}

    def open(self) -> None:
        if self._bus is not None:
            logger.warning("Bus already open: %s", self.interface)
            return
        can_filters = [{"can_id": CAN_FILTER_ID, "can_mask": CAN_FILTER_MASK, "extended": True}]
        self._bus = can.interface.Bus(
            channel=self.interface, bustype="socketcan",
            can_filters=can_filters, timeout=self.timeout,
        )
        logger.info("Opened: %s (filter id=0x%07X mask=0x%07X)", self.interface, CAN_FILTER_ID, CAN_FILTER_MASK)

    def close(self) -> None:
        self._running = False
        if self._bus is not None:
            self._bus.shutdown()
            logger.info("Closed: %s", self.interface)
        self._bus = None
        self._reasm.reset()

    def receive_one(self, timeout: Optional[float] = None) -> Optional[dict]:
        if self._bus is None:
            logger.error("Not opened")
            return None
        deadline = time.monotonic() + timeout if timeout is not None else float("inf")

        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic()) if timeout else 1.0
            try:
                msg = self._bus.recv(timeout=min(remaining, 1.0))
            except can.CanError as e:
                logger.error("CAN recv error: %s", e)
                time.sleep(0.1)
                continue

            if msg is None:
                time.sleep(0.05 if timeout is None else 0)
                continue

            self.stats["can_frames"] += 1
            sid = (msg.arbitration_id >> SUBJECT_ID_SHIFT) & SUBJECT_ID_MASK
            if sid != FIX2_SUBJECT_ID:
                continue

            for payload in self._reasm.feed(msg):
                result = parse_fix2(payload)
                if result is not None:
                    self.stats["fix2_messages"] += 1
                    return result
                self.stats["parse_errors"] += 1

        return None

    def monitor(self, callback: Callable[[dict], None], one_shot: bool = False) -> None:
        if self._bus is None:
            logger.error("Not opened")
            return
        self._running = True
        logger.info("Monitoring Fix2 on %s ...", self.interface)
        try:
            while self._running:
                result = self.receive_one(timeout=1.0)
                if result is not None:
                    try:
                        callback(result)
                    except Exception as e:
                        logger.error("Callback error: %s", e)
                    if one_shot:
                        break
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CAN Fix2 Monitor — DroneCAN gnss.Fix2 を CAN 経由で受信・表示",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="例:\n  %(prog)s --once\n  %(prog)s --monitor\n  %(prog)s --monitor --log-level DEBUG",
    )
    parser.add_argument("--interface", default="can0", help="CAN I/F 名 (default: can0)")
    parser.add_argument("--once", action="store_true", help="1件受信して詳細表示")
    parser.add_argument("--monitor", action="store_true", help="連続モニタリング (Ctrl+C)")
    parser.add_argument("--timeout", type=float, default=30.0, help="--once タイムアウト秒 (default:30)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not CAN_AVAILABLE:
        print("ERROR: python-can is not installed.", file=sys.stderr)
        print("  pip install python-can", file=sys.stderr)
        sys.exit(1)

    mon = CanFixMonitor(interface=args.interface)

    try:
        mon.open()

        if args.once:
            print(f"Waiting for Fix2 on {args.interface} (timeout={args.timeout:.0f}s) ...")
            result = mon.receive_one(timeout=args.timeout)
            if result is None:
                print("No Fix2 message received (timeout)")
                print(f"  CAN frames: {mon.stats['can_frames']}")
                sys.exit(1)
            print("─" * 55)
            print(format_fix2_verbose(result))
            print("─" * 55)
            sys.exit(0)

        elif args.monitor:
            print(f"Continuous monitoring on {args.interface} (Ctrl+C to stop)")
            print(HEADER_LINE)
            print("─" * 87)

            t0 = time.monotonic()
            prev = [-1]

            def cb(r):
                elapsed = time.monotonic() - t0
                mode = r.get("mode", -1)
                if prev[0] != -1 and prev[0] != 3 and mode == 3:
                    logger.info("=" * 50 + f"\n  >>> RTK FIXED! (t={elapsed:.1f}s) <<<\n" + "=" * 50)
                prev[0] = mode
                print(format_fix2(r, elapsed))

            mon.monitor(callback=cb, one_shot=False)

            print(f"\n--- Stats: frames={mon.stats['can_frames']}  fix2={mon.stats['fix2_messages']}  err={mon.stats['parse_errors']} ---")

        else:
            print(f"Waiting for Fix2 on {args.interface} (timeout={args.timeout:.0f}s) ...")
            result = mon.receive_one(timeout=args.timeout)
            if result is None:
                print("No Fix2 message received (timeout)")
                sys.exit(1)
            print("─" * 55)
            print(format_fix2_verbose(result))
            print("─" * 55)
            sys.exit(0)

    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(130)
    except can.CanError as e:
        logger.error("CAN error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Fatal: %s", e, exc_info=True)
        sys.exit(1)
    finally:
        mon.close()


if __name__ == "__main__":
    main()
