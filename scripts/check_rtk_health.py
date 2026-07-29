#!/usr/bin/env python3
"""
check_rtk_health.py — RTK Pipeline Comprehensive Health Check

One-shot diagnostic script for the entire RTK data pipeline:
  1. Rover F9P config verification (DGNSSMODE, UART2 baudrate, RTCM3 input)
  2. RTCM3 byte arrival check on UART2 (UBX-MON-MSGPP)
  3. RTCM relay pipeline connectivity (TCP port checks at each stage)
  4. RTCM3 stream capture & type analysis
  5. carrSoln status polling

Usage:
  # Full diagnostic (Mac side)
  python3 scripts/check_rtk_health.py

  # Only check Rover F9P (Raspi side)
  python3 scripts/check_rtk_health.py --rover-only

  # Custom configuration
  python3 scripts/check_rtk_health.py --base-tcp localhost:2101 \
      --raspi-ip 100.69.75.96 --rover-port /dev/ttyAMA4

  # Direct RTCM injection test (Mac → Rover)
  python3 scripts/check_rtk_health.py --inject-test --base-tcp localhost:2101 \
      --rover-port /dev/ttyACM0
"""

import argparse
import socket
import struct
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

# ────────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────────
RTCM3_PREAMBLE = 0xD3
RTCM3_LENGTH_MASK = 0x03

# UBX CFG-VALGET keys (from f9p_config_all.py)
_KEY_NAVHPG_DGNSSMODE = 0x20110011
_KEY_UART2_BAUDRATE = 0x40590001
_KEY_UART2INPROT_RTCM3X = 0x40590004
_KEY_UART2INPROT_UBX = 0x40590002
_KEY_RATE_MEAS = 0x30210001
_KEY_RATE_NAV = 0x30210002
_U4_KEYS = {_KEY_UART2_BAUDRATE}
_U2_KEYS = {_KEY_RATE_MEAS, _KEY_RATE_NAV}

# UBX-MON-VER poll
_MON_VER_POLL = bytes([0xB5, 0x62, 0x0A, 0x04, 0x00, 0x00, 0x0E, 0x34])

# UBX-MON-MSGPP poll
_MON_MSGPP_POLL = bytes([0xB5, 0x62, 0x0A, 0x06, 0x00, 0x00, 0x10, 0x3A])

# RTCM3 message type names
RTCM_NAMES = {
    1005: "Station ARP", 1006: "Station ARP+Ant",
    1074: "GPS MSM4", 1075: "GPS MSM5", 1077: "GPS MSM7",
    1084: "GLO MSM4", 1085: "GLO MSM5", 1087: "GLO MSM7",
    1094: "GAL MSM4", 1095: "GAL MSM5", 1097: "GAL MSM7",
    1124: "BDS MSM4", 1125: "BDS MSM5", 1127: "BDS MSM7",
    1230: "GLO Bias",
}
KEY_TYPES = [1005, 1006, 1074, 1084, 1094, 1124, 1230]

# ────────────────────────────────────────────────────────────────────────
# Output helpers
# ────────────────────────────────────────────────────────────────────────
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"
INFO = "\033[94mINFO\033[0m"


def _status_icon(ok: bool, warn: bool = False) -> str:
    if warn:
        return WARN
    return PASS if ok else FAIL


def _section(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def _check(name: str, ok: bool, detail: str = "", warn: bool = False):
    icon = _status_icon(ok, warn)
    print(f"  [{icon}] {name}")
    if detail:
        print(f"         {detail}")
    return ok


# ────────────────────────────────────────────────────────────────────────
# Section 1: Rover F9P Config (Serial → UBX CFG-VALGET)
# ────────────────────────────────────────────────────────────────────────
def _ubx_checksum(data: bytes) -> tuple[int, int]:
    """8-bit Fletcher checksum."""
    ck_a = 0
    ck_b = 0
    for b in data:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return ck_a, ck_b


def _build_cfg_valget(keys: list[str]) -> bytes:
    """Build UBX CFG-VALGET poll (layer=0, position=0)."""
    # UBX header: sync(2) + class(1) + id(1)
    # CFG-VALGET: cls=0x06, mid=0x8B
    # Payload: version(1)=0, layer(1)=0, position(2)=0, keys(4*N)
    payload = bytearray()
    payload.append(0x00)  # version
    payload.append(0x00)  # layer=0 (RAM)
    payload.extend(b'\x00\x00')  # position=0
    for key_name in keys:
        key_id = _key_name_to_id(key_name)
        if key_id is not None:
            payload.extend(struct.pack('<I', key_id))
    if len(payload) < 4:
        return b''

    cls_id = bytes([0x06, 0x8B])
    len_bytes = struct.pack('<H', len(payload))
    ck_a, ck_b = _ubx_checksum(cls_id + len_bytes + bytes(payload))
    return b'\xb5\x62' + cls_id + len_bytes + bytes(payload) + bytes([ck_a, ck_b])


def _key_name_to_id(name: str) -> Optional[int]:
    """Map CFG key name to key ID."""
    mapping = {
        "CFG-NAVHPG-DGNSSMODE": 0x20110011,
        "CFG-UART2-BAUDRATE": 0x40590001,
        "CFG-UART2INPROT-RTCM3X": 0x40590004,
        "CFG-UART2INPROT-UBX": 0x40590002,
        "CFG-UART2OUTPROT-UBX": 0x40590005,
        "CFG-RATE-MEAS": 0x30210001,
        "CFG-RATE-NAV": 0x30210002,
    }
    return mapping.get(name)


def _parse_valget(raw: bytes) -> dict[int, int]:
    """Parse CFG-VALGET response → {key_id: value}."""
    result = {}
    payload = raw[6:-2]
    if len(payload) < 8:
        return result
    pos = 4  # skip version, layer, position
    while pos + 4 <= len(payload):
        key_id = int.from_bytes(payload[pos:pos + 4], 'little')
        pos += 4
        if key_id in _U4_KEYS:
            if pos + 4 <= len(payload):
                result[key_id] = int.from_bytes(payload[pos:pos + 4], 'little')
                pos += 4
        elif key_id in _U2_KEYS:
            if pos + 2 <= len(payload):
                result[key_id] = int.from_bytes(payload[pos:pos + 2], 'little')
                pos += 2
        else:
            if pos < len(payload):
                result[key_id] = payload[pos]
                pos += 1
    return result


def check_rover_config(port: str, baud: int) -> dict:
    """Poll Rover F9P via serial for key config values."""
    result = {
        "alive": False,
        "dgnssmode": None,
        "uart2_baudrate": None,
        "uart2inprot_rtcm3x": None,
        "uart2inprot_ubx": None,
        "errors": [],
    }
    try:
        import serial
    except ImportError:
        result["errors"].append("pyserial not installed")
        return result

    keys_to_poll = [
        "CFG-NAVHPG-DGNSSMODE",
        "CFG-UART2-BAUDRATE",
        "CFG-UART2INPROT-RTCM3X",
        "CFG-UART2INPROT-UBX",
    ]

    try:
        ser = serial.Serial(port, baud, timeout=1.0)
        time.sleep(0.3)
        ser.reset_input_buffer()
    except Exception as e:
        result["errors"].append(f"Cannot open serial {port} @ {baud}: {e}")
        return result

    try:
        # ── Device alive check ──
        ser.reset_input_buffer()
        ser.write(_MON_VER_POLL)
        ser.flush()
        deadline = time.monotonic() + 3.0
        alive = False
        buf = b''
        while time.monotonic() < deadline:
            waiting = ser.in_waiting
            if waiting > 0:
                buf += ser.read(waiting)
            sync_pos = buf.find(b'\xb5\x62')
            if sync_pos >= 0 and len(buf) >= sync_pos + 8:
                if buf[sync_pos + 2] == 0x0A and buf[sync_pos + 3] == 0x04:
                    alive = True
                    break
            time.sleep(0.01)
        result["alive"] = alive
        if not alive:
            result["errors"].append("F9P not responding to UBX-MON-VER")
            return result

        # ── CFG-VALGET poll ──
        poll_msg = _build_cfg_valget(keys_to_poll)
        if not poll_msg:
            result["errors"].append("Failed to build CFG-VALGET message")
            return result

        ser.reset_input_buffer()
        ser.write(poll_msg)
        ser.flush()

        deadline = time.monotonic() + 5.0
        buf = b''
        while time.monotonic() < deadline:
            waiting = ser.in_waiting
            if waiting > 0:
                buf += ser.read(waiting)
            # Look for CFG-VALGET (0x06, 0x8B)
            sync_pos = buf.find(b'\xb5\x62')
            while sync_pos >= 0 and sync_pos + 8 <= len(buf):
                if buf[sync_pos + 2] == 0x06 and buf[sync_pos + 3] == 0x8B:
                    payload_len = buf[sync_pos + 4] | (buf[sync_pos + 5] << 8)
                    total_len = 8 + payload_len
                    if sync_pos + total_len <= len(buf):
                        raw = buf[sync_pos:sync_pos + total_len]
                        # Verify checksum
                        ck_a, ck_b = _ubx_checksum(raw[2:6 + payload_len])
                        if ck_a == raw[6 + payload_len] and ck_b == raw[6 + payload_len + 1]:
                            values = _parse_valget(raw)
                            if _KEY_NAVHPG_DGNSSMODE in values:
                                result["dgnssmode"] = values[_KEY_NAVHPG_DGNSSMODE]
                            if _KEY_UART2_BAUDRATE in values:
                                result["uart2_baudrate"] = values[_KEY_UART2_BAUDRATE]
                            if _KEY_UART2INPROT_RTCM3X in values:
                                result["uart2inprot_rtcm3x"] = values[_KEY_UART2INPROT_RTCM3X]
                            if _KEY_UART2INPROT_UBX in values:
                                result["uart2inprot_ubx"] = values[_KEY_UART2INPROT_UBX]
                            break
                sync_pos = buf.find(b'\xb5\x62', sync_pos + 2)
            else:
                time.sleep(0.01)
                continue
            break

    except Exception as e:
        result["errors"].append(f"Serial I/O error: {e}")
    finally:
        ser.close()

    return result


def check_mon_msgpp(port: str, baud: int) -> dict:
    """Poll UBX-MON-MSGPP for UART2 byte receive count."""
    result = {
        "uart2_bytes_received": 0,
        "uart2_parse_errors": 0,
        "errors": [],
    }
    try:
        import serial
    except ImportError:
        result["errors"].append("pyserial not installed")
        return result

    try:
        ser = serial.Serial(port, baud, timeout=1.0)
        time.sleep(0.3)
        ser.reset_input_buffer()

        ser.write(_MON_MSGPP_POLL)
        ser.flush()

        deadline = time.monotonic() + 3.0
        buf = b''
        while time.monotonic() < deadline:
            waiting = ser.in_waiting
            if waiting > 0:
                buf += ser.read(waiting)
            sync_pos = buf.find(b'\xb5\x62')
            while sync_pos >= 0 and sync_pos + 8 <= len(buf):
                if buf[sync_pos + 2] == 0x0A and buf[sync_pos + 3] == 0x06:
                    payload_len = buf[sync_pos + 4] | (buf[sync_pos + 5] << 8)
                    total_len = 8 + payload_len
                    if sync_pos + total_len <= len(buf):
                        raw = buf[sync_pos:sync_pos + total_len]
                        ck_a, ck_b = _ubx_checksum(raw[2:6 + payload_len])
                        if ck_a == raw[6 + payload_len] and ck_b == raw[6 + payload_len + 1]:
                            payload = raw[6:6 + payload_len]
                            # MON-MSGPP has entries: [portId:1][3][msgCnt:2][bytes:4][parseErrs:2][unused:2]
                            if len(payload) >= 12:
                                # First entry is typically UART1; we need UART2
                                # UART2 portId = 1 (0=I2C, 1=UART1, 2=UART2, 3=USB, ...)
                                # Each entry is 12 bytes
                                num_entries = len(payload) // 12
                                for i in range(num_entries):
                                    entry = payload[i * 12:(i + 1) * 12]
                                    port_id = entry[0]
                                    if port_id == 2:  # UART2
                                        result["uart2_bytes_received"] = int.from_bytes(entry[4:8], 'little')
                                        result["uart2_parse_errors"] = int.from_bytes(entry[8:10], 'little')
                                        break
                            break
                sync_pos = buf.find(b'\xb5\x62', sync_pos + 2)
            else:
                time.sleep(0.01)
                continue
            break

    except Exception as e:
        result["errors"].append(f"MON-MSGPP error: {e}")
    finally:
        ser.close()

    return result


# ────────────────────────────────────────────────────────────────────────
# Section 2: TCP Connectivity Check
# ────────────────────────────────────────────────────────────────────────
def check_tcp_port(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    """Check if a TCP port is reachable."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        t0 = time.monotonic()
        sock.connect((host, port))
        elapsed = time.monotonic() - t0
        sock.close()
        return True, f"connected in {elapsed:.2f}s"
    except ConnectionRefusedError:
        return False, "connection refused (port not listening)"
    except socket.timeout:
        return False, f"timeout after {timeout}s (host unreachable or firewall)"
    except socket.gaierror as e:
        return False, f"DNS/address error: {e}"
    except OSError as e:
        return False, f"OS error: {e}"


# ────────────────────────────────────────────────────────────────────────
# Section 3: RTCM3 Stream Capture & Analysis
# ────────────────────────────────────────────────────────────────────────
def capture_rtcm3(host: str, port: int, duration: float = 10.0) -> dict:
    """Capture RTCM3 from TCP and analyze message types."""
    result = {
        "connected": False,
        "total_frames": 0,
        "total_bytes": 0,
        "type_counter": Counter(),
        "errors": [],
    }
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        result["connected"] = True
        sock.settimeout(1.0)

        buf = bytearray()
        start = time.monotonic()
        while time.monotonic() - start < duration:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
            except socket.timeout:
                continue

            while len(buf) >= 6:
                if buf[0] != RTCM3_PREAMBLE:
                    buf.pop(0)
                    continue
                frame_len = ((buf[1] & RTCM3_LENGTH_MASK) << 8) | buf[2]
                total_len = 6 + frame_len
                if len(buf) < total_len:
                    break
                frame = bytes(buf[:total_len])
                buf = buf[total_len:]

                if len(frame) >= 6:
                    payload = frame[3:3 + frame_len]
                    if len(payload) >= 2:
                        msg_type = (payload[0] << 4) | (payload[1] >> 4)
                        result["type_counter"][msg_type] += 1
                        result["total_frames"] += 1
                        result["total_bytes"] += len(frame)

        sock.close()
    except ConnectionRefusedError:
        result["errors"].append(f"TCP {host}:{port} refused")
    except socket.timeout:
        result["errors"].append(f"TCP {host}:{port} timeout")
    except OSError as e:
        result["errors"].append(f"TCP error: {e}")

    return result


# ────────────────────────────────────────────────────────────────────────
# Section 4: Direct RTCM Injection Test
# ────────────────────────────────────────────────────────────────────────
def inject_rtcm3_to_serial(host: str, port: int, serial_port: str,
                            serial_baud: int, duration: float = 30.0) -> dict:
    """Connect TCP RTCM3 source directly to serial port."""
    result = {
        "tcp_connected": False,
        "serial_opened": False,
        "frames_forwarded": 0,
        "bytes_forwarded": 0,
        "errors": [],
    }
    try:
        import serial
    except ImportError:
        result["errors"].append("pyserial not installed")
        return result

    try:
        ser = serial.Serial(serial_port, serial_baud, timeout=0)
        result["serial_opened"] = True
    except Exception as e:
        result["errors"].append(f"Cannot open serial {serial_port}: {e}")
        return result

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        result["tcp_connected"] = True
        sock.settimeout(1.0)

        print(f"  Injecting RTCM3: {host}:{port} → {serial_port} @ {serial_baud} bps")
        print(f"  Duration: {duration}s (Ctrl+C to stop)")

        buf = bytearray()
        start = time.monotonic()
        last_report = start

        while time.monotonic() - start < duration:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
            except socket.timeout:
                continue

            while len(buf) >= 6:
                if buf[0] != RTCM3_PREAMBLE:
                    buf.pop(0)
                    continue
                frame_len = ((buf[1] & RTCM3_LENGTH_MASK) << 8) | buf[2]
                total_len = 6 + frame_len
                if len(buf) < total_len:
                    break
                frame = bytes(buf[:total_len])
                buf = buf[total_len:]

                ser.write(frame)
                ser.flush()
                result["frames_forwarded"] += 1
                result["bytes_forwarded"] += len(frame)

            now = time.monotonic()
            if now - last_report >= 5:
                elapsed = now - start
                fps = result["frames_forwarded"] / elapsed if elapsed > 0 else 0
                print(f"    t={elapsed:.0f}s: {result['frames_forwarded']} frames "
                      f"({result['bytes_forwarded']:,} bytes, {fps:.1f} fps)")
                last_report = now

    except KeyboardInterrupt:
        print("  Interrupted by user")
    except Exception as e:
        result["errors"].append(str(e))
    finally:
        try:
            sock.close()
        except Exception:
            pass
        try:
            ser.close()
        except Exception:
            pass

    return result


# ────────────────────────────────────────────────────────────────────────
# Main Diagnostic Runner
# ────────────────────────────────────────────────────────────────────────
def run_diagnostics(args) -> int:
    all_ok = True

    _section("RTK Pipeline Health Check")
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'ROVER ONLY' if args.rover_only else 'FULL PIPELINE'}")

    # ── 1. Rover F9P Config Check ────────────────────────────────────
    _section("1. Rover F9P Configuration")
    if not args.rover_port:
        print(f"  [{WARN}] No rover port specified. Use --rover-port")
    else:
        cfg = check_rover_config(args.rover_port, args.rover_baud)
        _check("Device alive (UBX-MON-VER)", cfg["alive"],
               "F9P responding" if cfg["alive"] else "No response — check serial/baudrate/power")

        if cfg["alive"]:
            dgnss = cfg.get("dgnssmode")
            dgnss_names = {0: "BOTH (Float+Fixed)", 3: "FIXED ONLY ⚠"}
            dgnss_name = dgnss_names.get(dgnss, f"UNKNOWN({dgnss})")
            dgnss_ok = dgnss == 0
            _check(f"CFG-NAVHPG-DGNSSMODE", dgnss_ok,
                   f"Value={dgnss} ({dgnss_name})" +
                   (" — DGNSSMODE=3 blocks FLOAT→FIXED transition!" if not dgnss_ok else ""))
            if not dgnss_ok:
                all_ok = False

            baud = cfg.get("uart2_baudrate")
            _check("CFG-UART2-BAUDRATE", baud == 115200,
                   f"Value={baud}" + ("" if baud == 115200 else f" — expected 115200!"))
            if baud != 115200:
                all_ok = False

            rtcm3x = cfg.get("uart2inprot_rtcm3x")
            _check("CFG-UART2INPROT-RTCM3X", rtcm3x == 1,
                   f"Value={rtcm3x}" + ("" if rtcm3x == 1 else " — must be 1 for RTCM3 input!"))
            if rtcm3x != 1:
                all_ok = False

            ubx_in = cfg.get("uart2inprot_ubx")
            _check("CFG-UART2INPROT-UBX", ubx_in == 1,
                   f"Value={ubx_in}" + ("" if ubx_in == 1 else " — UBX input should be 1"))

    # ── 2. UART2 Byte Reception (MON-MSGPP) ──────────────────────────
    _section("2. UART2 RTCM3 Data Arrival (MON-MSGPP)")
    if not args.rover_port:
        print(f"  [{WARN}] No rover port specified")
    else:
        msgs = check_mon_msgpp(args.rover_port, args.rover_baud)
        rx_bytes = msgs.get("uart2_bytes_received", 0)
        parse_errs = msgs.get("uart2_parse_errors", 0)
        has_data = rx_bytes > 0
        _check("UART2 bytes received", has_data,
               f"{rx_bytes:,} bytes" +
               ("" if has_data else " — NO RTCM3 data arriving on UART2!"))
        if has_data:
            _check("UART2 parse errors", parse_errs == 0,
                   f"{parse_errs}" +
                   ("" if parse_errs == 0 else " — data corruption on UART2!"))
            if parse_errs > 0:
                print(f"  [{INFO}] Parse errors suggest baudrate mismatch or signal integrity issue")
            else:
                print(f"  [{INFO}] RTCM3 data is arriving on UART2 — check carrSoln status next")
        else:
            all_ok = False
            print(f"  [{INFO}] No data on UART2. Possible causes:")
            print(f"         1. RTCM3 source not sending (check base station)")
            print(f"         2. tcp2serial/rtk_forwarder not running on Raspi")
            print(f"         3. UART2 wiring issue (RX2 pin)")
            print(f"         4. Baudrate mismatch")

    if args.rover_only:
        print()
        print("=" * 70)
        print(f"  Rover-only check complete. Use full mode for pipeline checks.")
        print("=" * 70)
        return 0 if all_ok else 1

    # ── 3. RTCM Relay Pipeline Connectivity ──────────────────────────
    _section("3. RTCM3 Relay Pipeline Connectivity")

    stages = []
    # Stage A: Base station TCP
    base_host, base_port = args.base_tcp.split(":") if ":" in args.base_tcp else (args.base_tcp, 2101)
    base_port = int(base_port)
    _check(f"[Stage A] Base station TCP ({base_host}:{base_port})", True,
           f"rtk_base_station_v2.py output port")
    ok, detail = check_tcp_port(base_host, base_port)
    _check(f"  └ TCP reachable", ok, detail)
    if not ok:
        all_ok = False
    stages.append(("[Stage A] Base station TCP", base_host, base_port, ok))

    # Stage B: NTRIP relay (Mac → Raspi)
    if args.raspi_ip:
        raspi_ip = args.raspi_ip
        relay_port = args.relay_port
        _check(f"[Stage B] NTRIP relay → Raspi ({raspi_ip}:{relay_port})", True,
               f"ntrip_relay.py → tcp2serial.py relay port")
        ok, detail = check_tcp_port(raspi_ip, relay_port)
        _check(f"  └ TCP reachable", ok, detail)
        if not ok:
            print(f"  [{INFO}] tcp2serial.py may not be running on Raspi.")
            print(f"          Start: ssh {args.raspi_user}@{raspi_ip} "
                  f"'python3 scripts/tcp2serial.py'")
            all_ok = False
        stages.append(("[Stage B] NTRIP relay", raspi_ip, relay_port, ok))

    # Stage C: rtk_forwarder on Raspi
    if args.raspi_ip and args.raspi_forwarder_port:
        ok, detail = check_tcp_port(args.raspi_ip, args.raspi_forwarder_port)
        _check(f"[Stage C] rtk_forwarder ({args.raspi_ip}:{args.raspi_forwarder_port})", ok, detail)
        stages.append(("[Stage C] rtk_forwarder", args.raspi_ip, args.raspi_forwarder_port, ok))

    # ── 4. RTCM3 Stream Capture & Analysis ───────────────────────────
    _section("4. RTCM3 Stream Content Analysis")
    print(f"  Capturing {base_host}:{base_port} for {args.capture_duration}s...")
    cap = capture_rtcm3(base_host, base_port, duration=args.capture_duration)
    _check("TCP connected", cap["connected"],
           "Source reachable" if cap["connected"] else "Cannot connect")
    if cap["total_frames"] > 0:
        _check("RTCM3 frames", True,
               f"{cap['total_frames']} frames, {cap['total_bytes']:,} bytes")
        print(f"  [{INFO}] Detected message types:")
        for mt in KEY_TYPES:
            count = cap["type_counter"].get(mt, 0)
            name = RTCM_NAMES.get(mt, f"Type {mt}")
            ok = count > 0
            icon = _status_icon(ok)
            print(f"    [{icon}] {mt:>4d} {name:<20s}: {count:>5d} frames")
            if not ok and mt in (1005, 1006):
                print(f"           ⚠  Station ARP missing — Rover cannot resolve base position!")
                print(f"           Fix: f9p_config_all.py --role base --mode write で再設定")
                all_ok = False

        missing = [mt for mt in KEY_TYPES if cap["type_counter"].get(mt, 0) == 0]
        if missing:
            print(f"  [{WARN}] Missing types: {missing}")
    else:
        _check("RTCM3 frames", False, "No RTCM3 frames received")
        print(f"  [{INFO}] Is rtk_base_station_v2.py running on the base station?")
        print(f"          Check: lsof -i TCP:{base_port}")
        all_ok = False

    # ── 5. RTCM3 Bypass Injection Test ───────────────────────────────
    if args.inject_test:
        _section("5. Direct RTCM3 Injection Test (Mac → Rover F9P)")
        if not args.inject_serial:
            print(f"  [{WARN}] Specify --inject-serial <port> for direct injection test")
        else:
            inj = inject_rtcm3_to_serial(
                base_host, base_port,
                args.inject_serial, args.inject_baud,
                duration=args.inject_duration,
            )
            if inj["tcp_connected"] and inj["serial_opened"]:
                _check(f"Direct injection ({base_host}:{base_port} → {args.inject_serial})",
                       inj["frames_forwarded"] > 0,
                       f"{inj['frames_forwarded']} frames forwarded")
                if inj["frames_forwarded"] > 0:
                    print(f"  [{INFO}] RTCM3 directly injected to Rover F9P. "
                          f"Monitor carrSoln now.")
            else:
                for e in inj["errors"]:
                    _check("Injection setup", False, e)

    # ── Final Summary ────────────────────────────────────────────────
    _section("Summary")
    print(f"  {'🎉 All checks PASSED' if all_ok else '⚠  Some checks FAILED — see above'}")
    print()
    print("  Recommended next actions:")
    if not all_ok:
        print("  1. Fix DGNSSMODE → run: f9p_config_all.py --role rover --mode write")
        print("  2. Restart pipeline: rtk_base_station_v2.py + rtk_forwarder_service.py")
        print("  3. Re-run this diagnostic to confirm fixes")
    else:
        print("  1. Monitor carrSoln: python3 scripts/check_rtk_health.py --monitor")
        print("  2. E2E test: python3 tests/e2e_rtk_pipeline_uart2_test.py --live")
    print("=" * 70)

    return 0 if all_ok else 1


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="check_rtk_health — RTK Pipeline Comprehensive Health Check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Full diagnostic\n"
            "  python3 scripts/check_rtk_health.py\n"
            "\n"
            "  # Rover only (on Raspi)\n"
            "  python3 scripts/check_rtk_health.py --rover-only --rover-port /dev/ttyAMA4\n"
            "\n"
            "  # With direct injection test\n"
            "  python3 scripts/check_rtk_health.py --inject-test --inject-serial /dev/ttyACM0\n"
            "\n"
            "  # Custom pipeline IPs\n"
            "  python3 scripts/check_rtk_health.py --base-tcp 100.80.225.4:2101 \\\n"
            "      --raspi-ip 100.69.75.96 --relay-port 2102\n"
        ),
    )
    # Rover config
    parser.add_argument("--rover-port", default=None,
                        help="Rover F9P serial port (e.g., /dev/ttyAMA4)")
    parser.add_argument("--rover-baud", type=int, default=115200,
                        help="Rover F9P baudrate (default: 115200)")
    parser.add_argument("--rover-only", action="store_true",
                        help="Only check Rover F9P config (skip pipeline checks)")

    # Base station
    parser.add_argument("--base-tcp", default="localhost:2101",
                        help="Base station TCP host:port (default: localhost:2101)")

    # NTRIP relay
    parser.add_argument("--raspi-ip", default=None,
                        help="Raspberry Pi Tailscale IP (e.g., 100.69.75.96)")
    parser.add_argument("--raspi-user", default="taki",
                        help="SSH username for Raspi (default: taki)")
    parser.add_argument("--relay-port", type=int, default=2102,
                        help="NTRIP relay TCP port on Raspi (default: 2102)")
    parser.add_argument("--raspi-forwarder-port", type=int, default=None,
                        help="rtk_forwarder TCP port on Raspi if applicable")

    # Stream capture
    parser.add_argument("--capture-duration", type=float, default=10.0,
                        help="RTCM3 capture duration in seconds (default: 10)")

    # Direct injection test
    parser.add_argument("--inject-test", action="store_true",
                        help="Run direct RTCM3 injection test (Mac → Rover F9P)")
    parser.add_argument("--inject-serial", default=None,
                        help="Serial port for direct injection (e.g., /dev/ttyACM0)")
    parser.add_argument("--inject-baud", type=int, default=115200,
                        help="Baudrate for direct injection (default: 115200)")
    parser.add_argument("--inject-duration", type=float, default=30.0,
                        help="Injection test duration (default: 30s)")

    args = parser.parse_args()
    return run_diagnostics(args)


if __name__ == "__main__":
    sys.exit(main())
