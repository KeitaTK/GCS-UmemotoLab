#!/usr/bin/env python3
"""
NMEA Fix Monitor — F9P USBポートの$GNGGAを解析してFix状態遷移を記録

現在の構成ではRaspberry Pi側UART2(/dev/ttyAMA4)にアクセスできないため、
F9P USBポートのNMEA GGAセンテンスからFix状態を監視する。
"""
import csv
import os
import sys
import time

import serial

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "rtcm_fix_transition.log")

FIX_NAMES = {0: "NoFix", 1: "GPS", 2: "DGPS", 4: "RTK_FIXED", 5: "RTK_FLOAT"}


def parse_gga(line: str):
    """Parse $GNGGA sentence, return dict or None."""
    parts = line.strip().split(",")
    if len(parts) < 10 or not parts[2]:
        return None
    try:
        lat_raw = float(parts[2])
        lat_deg = int(lat_raw / 100)
        lat = lat_deg + (lat_raw - lat_deg * 100) / 60.0
        if parts[3] == "S":
            lat = -lat

        lon_raw = float(parts[4])
        lon_deg = int(lon_raw / 100)
        lon = lon_deg + (lon_raw - lon_deg * 100) / 60.0
        if parts[5] == "W":
            lon = -lon

        fix = int(parts[6]) if parts[6] else 0
        sats = int(parts[7]) if parts[7] else 0
        hdop = float(parts[8]) if parts[8] else 0.0
        alt = float(parts[9]) if parts[9] else 0.0

        return {
            "fix": fix,
            "fix_name": FIX_NAMES.get(fix, f"UNKNOWN({fix})"),
            "sats": sats,
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "hdop": hdop,
        }
    except (ValueError, IndexError):
        return None


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/tty.usbmodem114301"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 38400
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    os.makedirs(LOG_DIR, exist_ok=True)
    f = open(LOG_FILE, "a", newline="")
    w = csv.writer(f)
    if os.path.getsize(LOG_FILE) == 0:
        w.writerow([
            "timestamp", "elapsed_sec", "fix", "fix_name",
            "numSV", "hdop", "lat", "lon", "alt", "transition"
        ])
        f.flush()

    ser = serial.Serial(port, baud, timeout=1.0)
    ser.reset_input_buffer()
    print(f"Monitoring {port} @ {baud} bps (NMEA GGA) ...")

    start = time.time()
    prev_fix = -1
    last_poll = start
    entries = 0

    try:
        while time.time() - start < duration:
            try:
                line = ser.readline()
            except Exception:
                time.sleep(0.1)
                continue

            if not line:
                continue

            try:
                decoded = line.decode("ascii", errors="ignore")
            except Exception:
                continue

            if not decoded.startswith("$GNGGA"):
                continue

            now = time.time()
            if now - last_poll < 2.0:  # throttle to ~2s intervals
                continue
            last_poll = now

            result = parse_gga(decoded)
            if result is None:
                continue

            elapsed = now - start
            ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
            fix = result["fix"]

            transition = ""
            if prev_fix != -1 and fix != prev_fix:
                transition = f">>> {FIX_NAMES.get(prev_fix, prev_fix)}→{FIX_NAMES.get(fix, fix)} <<<"
                print(f"  [!] FIX TRANSITION: {FIX_NAMES.get(prev_fix, '?')} → {FIX_NAMES.get(fix, '?')} at t={elapsed:.1f}s")

            prev_fix = fix

            w.writerow([
                ts, f"{elapsed:.1f}", fix, result["fix_name"],
                result["sats"], f"{result['hdop']:.2f}",
                f"{result['lat']:.7f}", f"{result['lon']:.7f}",
                f"{result['alt']:.1f}", transition,
            ])
            f.flush()
            entries += 1

            print(
                f"  t={elapsed:5.1f}s  fix={fix}({result['fix_name']})  "
                f"sats={result['sats']}  hdop={result['hdop']:.2f}  "
                f"lat={result['lat']:.7f}  lon={result['lon']:.7f}"
            )

    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        f.close()
        print(f"\nDone. {entries} entries logged to {LOG_FILE}")


if __name__ == "__main__":
    main()
