#!/usr/bin/env python3
"""
RTCM3 Frame Verification Script — /dev/ttyAMA4 上のRTCM3フレーム有無を確認

新アーキテクチャで /dev/ttyAMA4 にRTCM3補正データが正しく注入されているか
検証するための診断ツール。

使用例（Raspi上）:
  python scripts/verify_rtcm_on_uart.py --port /dev/ttyAMA4 --duration 30
  python scripts/verify_rtcm_on_uart.py --port /dev/ttyAMA4 --monitor
  python scripts/verify_rtcm_on_uart.py --port /dev/ttyAMA4 --once
"""

import argparse
import logging
import sys
import time
from collections import Counter

import serial

logger = logging.getLogger("verify_rtcm")

RTCM_PREAMBLE = 0xD3

RTCM_MSG_NAMES: dict[int, str] = {
    1005: "Stationary RTK Ref ARP",
    1074: "GPS MSM4",
    1075: "GPS MSM5",
    1077: "GPS MSM7",
    1084: "GLONASS MSM4",
    1085: "GLONASS MSM5",
    1087: "GLONASS MSM7",
    1094: "Galileo MSM4",
    1095: "Galileo MSM5",
    1097: "Galileo MSM7",
    1124: "BeiDou MSM4",
    1125: "BeiDou MSM5",
    1127: "BeiDou MSM7",
    1230: "GLONASS Code-Phase Biases",
    1019: "GPS Ephemeris",
    1020: "GLONASS Ephemeris",
    1045: "Galileo F/NAV Ephemeris",
    1046: "Galileo I/NAV Ephemeris",
    4072: "u-blox Proprietary",
}


def parse_rtcm_message_type(frame: bytes) -> int:
    """Extract 12-bit message type from RTCM3 frame header."""
    if len(frame) < 7:
        return -1
    return ((frame[3] & 0xFF) << 4) | ((frame[4] >> 4) & 0x0F)


def parse_rtcm_frame_length(buf: memoryview) -> int:
    """Parse RTCM3 10-bit message length. Returns total frame length or 0."""
    if len(buf) < 6 or buf[0] != RTCM_PREAMBLE:
        return 0
    msg_len = ((buf[1] & 0x03) << 8) | buf[2]
    return 6 + msg_len


def verify_port(port: str, baudrate: int, timeout: float = 30.0) -> dict:
    """Open serial port and count RTCM3 frames."""
    results = {
        "total_frames": 0,
        "type_counter": Counter(),
        "byte_count": 0,
        "first_frame_time": None,
        "last_frame_time": None,
        "errors": [],
    }

    try:
        ser = serial.Serial(port, baudrate, timeout=1.0)
        logger.info("Opened %s @ %d bps (timeout=%.0fs)", port, baudrate, timeout)
    except serial.SerialException as e:
        results["errors"].append(f"Cannot open {port}: {e}")
        return results

    buffer = bytearray()
    start = time.monotonic()

    try:
        while time.monotonic() - start < timeout:
            try:
                chunk = ser.read(1024)
            except serial.SerialException as e:
                results["errors"].append(f"Serial read error: {e}")
                time.sleep(0.5)
                continue

            if not chunk:
                continue

            buffer.extend(chunk)

            while len(buffer) >= 6:
                if buffer[0] != RTCM_PREAMBLE:
                    buffer.pop(0)
                    continue

                total_len = parse_rtcm_frame_length(memoryview(buffer))
                if total_len == 0 or len(buffer) < total_len:
                    break

                frame = bytes(buffer[:total_len])
                buffer = buffer[total_len:]

                msg_type = parse_rtcm_message_type(frame)
                results["total_frames"] += 1
                results["byte_count"] += len(frame)
                results["type_counter"][msg_type] += 1
                results["last_frame_time"] = time.monotonic()

                if results["first_frame_time"] is None:
                    results["first_frame_time"] = time.monotonic()

                type_name = RTCM_MSG_NAMES.get(msg_type, "?")
                logger.debug(
                    "  Frame #%4d: type=%4d (%s), size=%dB",
                    results["total_frames"], msg_type, type_name, len(frame)
                )

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        ser.close()

    return results


def verify_once(port: str, baudrate: int) -> bool:
    """Read one RTCM3 frame (or timeout) and report."""
    try:
        ser = serial.Serial(port, baudrate, timeout=10.0)
        logger.info("Opened %s @ %d bps (waiting for frame...)", port, baudrate)
    except serial.SerialException as e:
        print(f"ERROR: Cannot open {port}: {e}")
        return False

    buffer = bytearray()
    try:
        while True:
            chunk = ser.read(1024)
            if not chunk:
                print("ERROR: No data received within 10s timeout")
                print("  → Is rtk-uart2-inject service running?")
                print("  → Is rtk_base_station_v2.py running on Mac?")
                return False

            buffer.extend(chunk)

            while len(buffer) >= 6:
                if buffer[0] != RTCM_PREAMBLE:
                    buffer.pop(0)
                    continue

                total_len = parse_rtcm_frame_length(memoryview(buffer))
                if total_len == 0 or len(buffer) < total_len:
                    break

                frame = bytes(buffer[:total_len])
                msg_type = parse_rtcm_message_type(frame)
                type_name = RTCM_MSG_NAMES.get(msg_type, "UNKNOWN")

                print()
                print("  ✅ RTCM3 frame detected!")
                print(f"     Port:     {port}")
                print(f"     Preamble: 0xD3")
                print(f"     Type:     {msg_type} ({type_name})")
                print(f"     Size:     {len(frame)} bytes")
                print(f"     Raw:      {frame[:32].hex()}...")
                return True

    except KeyboardInterrupt:
        pass
    finally:
        ser.close()

    return False


def _print_summary(results: dict) -> None:
    """Print verification summary."""
    print()
    print("=" * 60)
    print("RTCM3 Frame Verification Summary")
    print("=" * 60)

    if results["errors"]:
        for e in results["errors"]:
            print(f"  ❌ ERROR: {e}")
        print("=" * 60)
        return

    total = results["total_frames"]
    if total == 0:
        print("  ❌ No RTCM3 frames detected!")
        print()
        print("  Troubleshooting:")
        print("    1. sudo systemctl status rtk-uart2-inject")
        print("    2. Check rtk_base_station_v2.py on Mac (TCP:2101)")
        print("    3. Verify GPIO12/13 → USB-Serial → F9P UART2 RX2 wiring")
        print("    4. python rtk_tools/f9p_rover_config.py --verify-only")
    else:
        elapsed = (results["last_frame_time"] or 0) - (results["first_frame_time"] or 0)
        rate = total / elapsed if elapsed > 0 else 0
        byte_rate = results["byte_count"] / elapsed if elapsed > 0 else 0

        print(f"  ✅ Total frames:    {total}")
        print(f"  ✅ Total bytes:     {results['byte_count']}")
        print(f"  ✅ Elapsed:         {elapsed:.1f}s")
        print(f"  ✅ Frame rate:      {rate:.1f} frames/sec")
        print(f"  ✅ Byte rate:       {byte_rate:.1f} bytes/sec")
        print()
        print("  Message types:")
        for msg_type, count in results["type_counter"].most_common():
            type_name = RTCM_MSG_NAMES.get(msg_type, f"UNKNOWN({msg_type})")
            print(f"    Type {msg_type:>4d} ({type_name:<40s}): {count:>4d}")

        has_msm4 = any(t in results["type_counter"] for t in [1074, 1084, 1094, 1124])
        has_msm7 = any(t in results["type_counter"] for t in [1077, 1087, 1097, 1127])
        has_1005 = 1005 in results["type_counter"]

        print()
        print("  RTK quality indicators:")
        print(f"    Stationary Ref (1005):    {'✅' if has_1005 else '⚠️ '}")
        print(f"    MSM4 (GPS/GLO/GAL/BDS):   {'✅' if has_msm4 else '⚠️ '}")
        print(f"    MSM7 (GPS/GLO/GAL/BDS):   {'✅' if has_msm7 else '⚠️ '}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="RTCM3 Frame Verification — /dev/ttyAMA4 上のRTCM3有無を確認",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "使用例:\n"
            "  python scripts/verify_rtcm_on_uart.py --port /dev/ttyAMA4 --duration 30\n"
            "  python scripts/verify_rtcm_on_uart.py --port /dev/ttyAMA4 --monitor\n"
            "  python scripts/verify_rtcm_on_uart.py --port /dev/ttyAMA4 --once\n"
        ),
    )
    parser.add_argument(
        "--port", default="/dev/ttyAMA4",
        help="Serial port (default: /dev/ttyAMA4)"
    )
    parser.add_argument(
        "--baud", type=int, default=115200,
        help="Baudrate (default: 115200)"
    )
    parser.add_argument(
        "--duration", type=float, default=30.0,
        help="Monitoring duration in seconds (default: 30)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Wait for single RTCM3 frame and exit"
    )
    parser.add_argument(
        "--monitor", action="store_true",
        help="Continuous monitoring (Ctrl+C to stop)"
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        if args.once:
            ok = verify_once(args.port, args.baud)
            sys.exit(0 if ok else 1)
        elif args.monitor:
            results = verify_port(args.port, args.baud, timeout=86400)
            _print_summary(results)
        else:
            print(f"Verifying RTCM3 on {args.port} ({args.duration}s)...")
            results = verify_port(args.port, args.baud, timeout=args.duration)
            _print_summary(results)
            sys.exit(0 if results["total_frames"] > 0 else 1)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()
