#!/usr/bin/env python3
"""
can_rtcm_diagnose.py — CAN経由RTCM注入 診断・設定スクリプト

Rover F9P側の UART1INPROT-RTCM3X 確認・設定を行います（Raspi UART4経由）。
Pixhawk側 GPS_INJECT_TO は QGroundControl / mavproxy で別途確認が必要。

Usage (on Raspberry Pi):
  python3 scripts/can_rtcm_diagnose.py --port /dev/ttyAMA4 --check-only
  python3 scripts/can_rtcm_diagnose.py --port /dev/ttyAMA4 --fix
  python3 scripts/can_rtcm_diagnose.py --port /dev/ttyAMA4 --auto
"""

import argparse, logging, struct, sys, time
from typing import Optional
import serial

logger = logging.getLogger("can_rtcm_diagnose")

KEY_UART1INPROT_UBX    = 0x10730001
KEY_UART1INPROT_NMEA   = 0x10730002
KEY_UART1INPROT_RTCM3X = 0x10730004
KEY_TMODE_MODE = 0x20030001

CARRSOLN_NAMES = {0: "NONE", 1: "FLOAT", 2: "FIXED"}
TMODE_NAMES = {0: "DISABLED", 1: "SURVEY-IN", 2: "FIXED"}

def _ubx_checksum(data):
    ck_a = ck_b = 0
    for b in data:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return ck_a, ck_b

def build_cfg_valget(key_ids):
    payload = struct.pack("<BBH", 0, 0, 0)
    for kid in key_ids:
        payload += struct.pack("<I", kid)
    plen = len(payload)
    body = bytes([0x06, 0x8B]) + struct.pack("<H", plen) + payload
    ck_a, ck_b = _ubx_checksum(body)
    return bytes([0xB5, 0x62]) + body + bytes([ck_a, ck_b])

def build_cfg_valset(key_id, value, layers=1):
    payload = struct.pack("<BBH", 0, layers, 0)
    payload += struct.pack("<I", key_id) + struct.pack("B", value)
    plen = len(payload)
    body = bytes([0x06, 0x8A]) + struct.pack("<H", plen) + payload
    ck_a, ck_b = _ubx_checksum(body)
    return bytes([0xB5, 0x62]) + body + bytes([ck_a, ck_b])

def scan_ubx_frames(buf):
    frames = []
    idx = 0
    while True:
        sync = buf.find(b"\xb5\x62", idx)
        if sync < 0:
            break
        if sync + 8 > len(buf):
            break
        cls, mid = buf[sync+2], buf[sync+3]
        plen = buf[sync+4] | (buf[sync+5] << 8)
        total = 8 + plen
        if sync + total > len(buf):
            break
        frame = buf[sync:sync+total]
        ck_a, ck_b = _ubx_checksum(frame[2:6+plen])
        if ck_a == frame[6+plen] and ck_b == frame[7+plen]:
            frames.append((cls, mid, frame))
        idx = sync + 2
    return frames

def parse_valget_response(frame):
    if len(frame) < 8:
        return {}
    plen = frame[4] | (frame[5] << 8)
    payload = frame[6:6+plen]
    result = {}
    pos = 4
    while pos + 4 <= len(payload):
        key_id = struct.unpack("<I", payload[pos:pos+4])[0]
        pos += 4
        if pos < len(payload):
            result[key_id] = payload[pos]
            pos += 1
    return result

def parse_nav_pvt(frame):
    if len(frame) < 48:
        return None
    plen = frame[4] | (frame[5] << 8)
    if plen < 44:
        return None
    payload = frame[6:6+plen]
    fix_type = payload[20]
    flags = payload[21]
    num_sv = payload[23]
    h_acc = struct.unpack("<I", payload[40:44])[0] / 1000.0
    cs = (flags >> 6) & 0x03
    return {"carrSoln": cs, "carrSoln_name": CARRSOLN_NAMES.get(cs, "?"),
            "fixType": fix_type, "numSV": num_sv, "hAcc": h_acc}

# ---------------------------------------------------------------------------
class CanRtcmDiagnose:
    def __init__(self, port, baud=115200):
        self.port = port
        self.baud = baud
        self._ser = None

    def open(self):
        self._ser = serial.Serial(self.port, self.baud, timeout=2.0)
        self._ser.reset_input_buffer()

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()

    def _txrx(self, msg, wait=1.0):
        self._ser.reset_input_buffer()
        self._ser.write(msg)
        self._ser.flush()
        time.sleep(wait)
        return self._ser.read(8192)

    def check_uart1_inprot(self):
        print("\n" + "=" * 60)
        print("  Rover F9P: UART1 Input Protocol Check")
        print("=" * 60)
        poll = build_cfg_valget([KEY_UART1INPROT_UBX, KEY_UART1INPROT_NMEA,
                                  KEY_UART1INPROT_RTCM3X, KEY_TMODE_MODE])
        buf = self._txrx(poll, 1.5)
        frames = scan_ubx_frames(buf)
        result = {"rtcm3x": None, "tmode": None, "is_rover": False,
                  "rtcm3x_enabled": False}
        for cls, mid, frame in frames:
            if cls == 0x06 and mid == 0x8B:
                vals = parse_valget_response(frame)
                if KEY_UART1INPROT_UBX in vals:
                    print(f"  UART1INPROT-UBX    = {vals[KEY_UART1INPROT_UBX]}")
                if KEY_UART1INPROT_NMEA in vals:
                    print(f"  UART1INPROT-NMEA   = {vals[KEY_UART1INPROT_NMEA]}")
                if KEY_UART1INPROT_RTCM3X in vals:
                    v = vals[KEY_UART1INPROT_RTCM3X]
                    result["rtcm3x"] = v
                    result["rtcm3x_enabled"] = (v == 1)
                    s = "✅ ENABLED" if v == 1 else "❌ DISABLED"
                    print(f"  UART1INPROT-RTCM3X = {v}  {s}")
                if KEY_TMODE_MODE in vals:
                    v = vals[KEY_TMODE_MODE]
                    result["tmode"] = v
                    result["is_rover"] = (v == 0)
                    r = "ROVER ✅" if v == 0 else f"BASE? ({TMODE_NAMES.get(v,'?')})"
                    print(f"  TMODE-MODE         = {v} ({TMODE_NAMES.get(v,'?')}) → {r}")
        return result

    def set_uart1_rtcm3(self):
        print("\n  Setting CFG-UART1INPROT-RTCM3X = 1 ...")
        msg = build_cfg_valset(KEY_UART1INPROT_RTCM3X, 1, 1)
        buf = self._txrx(msg, 1.0)
        for cls, mid, _ in scan_ubx_frames(buf):
            if cls == 0x05:
                print(f"  {'✅ ACK-ACK' if mid == 0x01 else '❌ ACK-NAK'}")
                return mid == 0x01
        print("  ⚠️  No ACK (OK in mixed stream)")
        return True

    def verify_uart1_rtcm3(self):
        poll = build_cfg_valget([KEY_UART1INPROT_RTCM3X])
        buf = self._txrx(poll, 1.5)
        for cls, mid, frame in scan_ubx_frames(buf):
            if cls == 0x06 and mid == 0x8B:
                vals = parse_valget_response(frame)
                if KEY_UART1INPROT_RTCM3X in vals:
                    v = vals[KEY_UART1INPROT_RTCM3X]
                    print(f"  Verify: RTCM3X = {v} {'✅' if v==1 else '❌'}")
                    return v == 1
        return False

    def poll_carrsoln(self, timeout=5.0):
        deadline = time.time() + timeout
        buf = b""
        while time.time() < deadline:
            w = self._ser.in_waiting
            if w > 0:
                buf += self._ser.read(w)
            for cls, mid, frame in scan_ubx_frames(buf):
                if cls == 0x01 and mid == 0x07:
                    return parse_nav_pvt(frame)
            if w == 0:
                time.sleep(0.05)
        return None

    def monitor(self, count=3, interval=60.0):
        print("\n" + "=" * 70)
        print(f"  carrSoln Monitor — {count} polls x {interval}s")
        print("=" * 70)
        samples = []
        max_cs = -1
        for i in range(1, count + 1):
            r = self.poll_carrsoln(5.0)
            if r is None:
                print(f"  [{i}/{count}] NO RESPONSE")
            else:
                cs = r["carrSoln"]
                max_cs = max(max_cs, cs)
                samples.append(r)
                print(f"  [{i}/{count}] carrSoln={cs}({r['carrSoln_name']}) "
                      f"fixType={r['fixType']} numSV={r['numSV']} hAcc={r['hAcc']:.3f}m")
                if len(samples) >= 2 and samples[-2]["carrSoln"] == 0 and cs >= 1:
                    print(f"    >>> FLOAT reached! <<<")
                elif len(samples) >= 2 and samples[-2]["carrSoln"] == 1 and cs == 2:
                    print(f"    >>> FIXED reached! <<<")
            if i < count:
                time.sleep(interval)
        final = samples[-1]["carrSoln"] if samples else -1
        fname = CARRSOLN_NAMES.get(final, "N/A")
        print(f"\n  Max carrSoln: {max_cs}  Final: {final}({fname})")
        return {"max_carrsoln": max_cs, "final_carrsoln": final,
                "samples": samples}

# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="CAN RTCM injection Rover F9P config")
    p.add_argument("--port", default="/dev/ttyAMA4")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--fix", action="store_true")
    p.add_argument("--monitor", action="store_true")
    p.add_argument("--auto", action="store_true")
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--interval", type=float, default=60.0)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    d = CanRtcmDiagnose(args.port, args.baud)
    try:
        d.open()
        if args.check_only:
            r = d.check_uart1_inprot()
            if not r["rtcm3x_enabled"]:
                print("\n  💡 Run with --fix to enable UART1 RTCM3 input.")
        elif args.fix:
            r = d.check_uart1_inprot()
            if r["rtcm3x_enabled"]:
                print("\n  ✅ Already enabled.")
            else:
                d.set_uart1_rtcm3()
                d.verify_uart1_rtcm3()
        elif args.monitor:
            d.monitor(args.count, args.interval)
        elif args.auto:
            print("\n" + "#" * 50)
            print("#  CAN RTCM Injection — Auto Config")
            print("#" * 50)
            r = d.check_uart1_inprot()
            rtcm3_before = 0 if not r["rtcm3x_enabled"] else 1
            if not r["is_rover"]:
                print("\n  ⚠️  Not in rover mode — monitor anyway")
            if not r["rtcm3x_enabled"]:
                d.set_uart1_rtcm3()
                d.verify_uart1_rtcm3()
            print("\n  📡 Monitoring carrSoln (wait 2-3min if RTCM just started)...")
            summary = d.monitor(args.count, args.interval)
            print("\n" + "=" * 50)
            print("  REPORT")
            print("=" * 50)
            print(f"  UART1INPROT-RTCM3X  before: {rtcm3_before}")
            print(f"  UART1INPROT-RTCM3X  after:  1")
            print(f"  Max carrSoln:       {summary['max_carrsoln']}")
            print(f"  Final carrSoln:     {summary['final_carrsoln']}")
            print("=" * 50)
        else:
            d.check_uart1_inprot()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        d.close()

if __name__ == "__main__":
    main()
