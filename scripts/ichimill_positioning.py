#!/usr/bin/env python3
"""
ichimill_positioning.py — イチミルNTRIP基地局 全自動測位スクリプト

処理フロー:
  1. シリアル接続 (/dev/tty.usbmodem114301, 115200)
  2. UBX-CFG-VALSET: TMODE3=0 (無効化)
  3. UBX-CFG-VALSET: CFG-UART1INPROT-RTCM3X=1 (key_id=0x40520004)
  4. NTRIP受信スレッド起動 (GET+Basic認証+GGA+RTCM3→シリアル注入)
  5. UBX-NAV-PVT ポーリング: fixType=6, carrSoln=2 を最大300秒待つ
  6. FIXED後 600秒間 1秒間隔で NAV-PVT 収集 (carrSoln=2 のみ)
  7. lat/lon/height の平均と標準偏差を算出
  8. config/base_station.json 更新
  9. TMODE3=2 (FIXED) + LAT/LON/HEIGHT 書き込み
 10. 最終結果表示

Usage:
  python scripts/ichimill_positioning.py
  python scripts/ichimill_positioning.py --port /dev/tty.usbmodem114301
  python scripts/ichimill_positioning.py --collect-sec 600 --fix-timeout 300
"""

import argparse
import base64
import json
import logging
import math
import os
import signal
import socket
import statistics
import struct
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import serial
import yaml
from pyubx2 import UBXMessage, POLL

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FIX_TYPE_NAMES = {
    0: "NO_FIX", 1: "DEAD_RECKONING", 2: "2D", 3: "3D",
    4: "GNSS+DR", 5: "TIME_ONLY",
}
CARR_SOLN_NAMES = {0: "NO_RTK", 1: "FLOAT", 2: "FIXED"}

# UBX message IDs
UBX_CLS_NAV = 0x01
UBX_MID_NAV_PVT = 0x07
UBX_CLS_CFG = 0x06
UBX_MID_ACK_ACK = 0x01
UBX_MID_ACK_NAK = 0x00

# Layer bitmask
LAYER_RAM = 1
LAYER_BBR = 2
LAYER_FLASH = 4
LAYER_ALL = LAYER_RAM | LAYER_BBR | LAYER_FLASH

# NTRIP config
NTRIP_HOST = "ntrip.ales-corp.co.jp"
NTRIP_PORT = 2101
NTRIP_MOUNTPOINT = "32M7NHS"
NTRIP_USER = "6y8swddj"
NTRIP_PASS = "xxu2w5"
NTRIP_USER_AGENT = "NTRIP PythonClient"

# GGA defaults (ichimill reference position)
GGA_LAT = 36.069351
GGA_LON = 136.241050
GGA_ALT = 56.25
GGA_INTERVAL_SEC = 10

# Defaults
DEFAULT_PORT = "/dev/tty.usbmodem114301"
DEFAULT_BAUDRATE = 115200
DEFAULT_FIX_TIMEOUT = 300
DEFAULT_COLLECT_SEC = 600
DEFAULT_COLLECT_INTERVAL = 1.0

BASE_STATION_JSON = "config/base_station.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("ichimill_positioning")

# ---------------------------------------------------------------------------
# NMEA GGA builder
# ---------------------------------------------------------------------------

def _ddm_to_nmea(deg: float) -> str:
    """Convert decimal degrees to NMEA DDMM.MMMM format string (no hemisuffix)."""
    d = int(abs(deg))
    m = (abs(deg) - d) * 60.0
    return f"{d:02d}{m:07.4f}"


def _nmea_checksum(sentence: str) -> str:
    """Calculate NMEA checksum (XOR of chars between $ and *)."""
    ck = 0
    for ch in sentence:
        ck ^= ord(ch)
    return f"{ck:02X}"


def build_gga(lat: float, lon: float, alt_m: float) -> bytes:
    """Build a $GPGGA sentence for NTRIP injection.

    Returns: bytes like b"$GPGGA,...*CS\\r\\n"
    """
    now = datetime.utcnow()
    time_str = now.strftime("%H%M%S")
    lat_str = _ddm_to_nmea(lat)
    lon_str = _ddm_to_nmea(lon)
    lat_ns = "N" if lat >= 0 else "S"
    lon_ew = "E" if lon >= 0 else "W"

    body = (
        f"GPGGA,{time_str},{lat_str},{lat_ns},{lon_str},{lon_ew},"
        f"1,12,1.0,{alt_m:.1f},M,0.0,M,,"
    )
    ck = _nmea_checksum(body)
    return f"${body}*{ck}\r\n".encode("ascii")


# ---------------------------------------------------------------------------
# UBX helpers
# ---------------------------------------------------------------------------

def build_cfg_valset(cfg_data: list, layers: int = LAYER_RAM) -> bytes:
    """Build a UBX-CFG-VALSET message using pyubx2."""
    msg = UBXMessage.config_set(layers, 0, cfg_data)
    return msg.serialize()


def build_nav_pvt_poll() -> bytes:
    """Build a UBX-NAV-PVT poll request."""
    msg = UBXMessage(UBX_CLS_NAV, UBX_MID_NAV_PVT, POLL)
    return msg.serialize()


def read_ubx_response(
    ser: serial.Serial,
    cls: int,
    mid: int,
    timeout: float = 3.0,
) -> bytes | None:
    """Read a specific UBX response frame from serial, with sync-pattern scanning.

    Handles mixed RTCM3 + UBX streams by scanning for 0xB5 0x62 sync.
    """
    deadline = time.monotonic() + timeout
    buf = b""

    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting > 0:
            buf += ser.read(waiting)

        idx = 0
        while True:
            sync_pos = buf.find(b"\xb5\x62", idx)
            if sync_pos < 0:
                if len(buf) > 0 and buf[-1:] == b"\xb5":
                    buf = b"\xb5"
                elif len(buf) > 0:
                    buf = b""
                break

            if sync_pos + 6 > len(buf):
                buf = buf[sync_pos:]
                break

            frame_cls = buf[sync_pos + 2]
            frame_id = buf[sync_pos + 3]
            payload_len = buf[sync_pos + 4] | (buf[sync_pos + 5] << 8)
            total_len = 8 + payload_len

            if sync_pos + total_len > len(buf):
                buf = buf[sync_pos:]
                break

            frame = buf[sync_pos : sync_pos + total_len]

            # Verify checksum
            ck_a = ck_b = 0
            for b in frame[2 : 6 + payload_len]:
                ck_a = (ck_a + b) & 0xFF
                ck_b = (ck_b + ck_a) & 0xFF
            expected_ck_a = frame[6 + payload_len]
            expected_ck_b = frame[6 + payload_len + 1]

            if ck_a == expected_ck_a and ck_b == expected_ck_b:
                if frame_cls == cls and frame_id == mid:
                    return frame
                idx = sync_pos + total_len
            else:
                idx = sync_pos + 2

        if not ser.in_waiting:
            time.sleep(0.01)

    return None


def parse_nav_pvt(raw: bytes) -> dict | None:
    """Parse UBX-NAV-PVT raw frame into a dict with key fields.

    UBX-NAV-PVT frame structure (92 bytes payload):
      offset 20: fixType (U1)
      offset 21: flags (U1)
      offset 22: flags2 (U1) → carrSoln = bits 6-7
      offset 23: numSV (U1)
      offset 24: lon (I4, deg * 1e-7)
      offset 28: lat (I4, deg * 1e-7)
      offset 32: height (I4, mm)
      offset 40: hAcc (U4, mm)
    """
    if len(raw) < 34:
        return None

    payload = raw[6:-2]  # strip sync(2) + checksum(2)
    if len(payload) < 34:
        return None

    try:
        fix_type = payload[20]
        flags2 = payload[22]
        carr_soln = (flags2 >> 6) & 0x03
        num_sv = payload[23]
        lon_e7 = int.from_bytes(payload[24:28], "little", signed=True)
        lat_e7 = int.from_bytes(payload[28:32], "little", signed=True)
        height_mm = int.from_bytes(payload[32:36], "little", signed=True)
        h_acc = int.from_bytes(payload[40:44], "little")  # mm

        return {
            "fix_type": fix_type,
            "carr_soln": carr_soln,
            "num_sv": num_sv,
            "lat": lat_e7 / 1e7,
            "lon": lon_e7 / 1e7,
            "height": height_mm / 1000.0,
            "h_acc": h_acc / 1000.0,
        }
    except (IndexError, struct.error):
        return None


# ---------------------------------------------------------------------------
# NTRIP + GGA client (threaded)
# ---------------------------------------------------------------------------

class NtripGgaClient:
    """NTRIP client that fetches RTCM3 stream and injects GGA periodically.

    Runs a background thread for the NTRIP connection.
    Writes received RTCM3 bytes to a shared serial port (thread-safe via lock).
    """

    def __init__(
        self,
        serial_port: serial.Serial,
        host: str = NTRIP_HOST,
        port: int = NTRIP_PORT,
        mountpoint: str = NTRIP_MOUNTPOINT,
        username: str = NTRIP_USER,
        password: str = NTRIP_PASS,
        user_agent: str = NTRIP_USER_AGENT,
        gga_lat: float = GGA_LAT,
        gga_lon: float = GGA_LON,
        gga_alt: float = GGA_ALT,
        gga_interval: float = GGA_INTERVAL_SEC,
        timeout: float = 10.0,
    ):
        self._ser = serial_port
        self._host = host
        self._port = port
        self._mountpoint = mountpoint
        self._username = username
        self._password = password
        self._user_agent = user_agent
        self._gga_lat = gga_lat
        self._gga_lon = gga_lon
        self._gga_alt = gga_alt
        self._gga_interval = gga_interval
        self._timeout = timeout

        self._sock: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._ser_lock = threading.Lock()
        self._total_bytes = 0
        self._total_frames = 0
        self._last_log = time.monotonic()

        logger.info(
            "NTRIP client init: %s:%d/%s (GGA every %.0fs at %.6f,%.6f,%.1fm)",
            host, port, mountpoint, gga_interval, gga_lat, gga_lon, gga_alt,
        )

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def total_frames(self) -> int:
        return self._total_frames

    def start(self):
        """Start the NTRIP client in a background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("NTRIP client thread started")

    def stop(self):
        """Signal the NTRIP client to stop."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("NTRIP client stopped")

    def _build_ntrip_request(self) -> bytes:
        lines = [
            f"GET /{self._mountpoint} HTTP/1.0",
            f"User-Agent: {self._user_agent}",
        ]
        if self._username and self._password:
            token = base64.b64encode(
                f"{self._username}:{self._password}".encode("utf-8")
            ).decode("ascii")
            lines.append(f"Authorization: Basic {token}")
        return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")

    def _run(self):
        """Main NTRIP loop: connect → GGA → RTCM3 receive → serial write."""
        while self._running:
            try:
                self._connect_and_stream()
            except Exception as exc:
                logger.warning("NTRIP error: %s — reconnecting in 5s", exc)
            if self._running:
                time.sleep(5.0)

    def _connect_and_stream(self):
        """Single NTRIP connection session."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self._timeout)

        logger.info("Connecting to NTRIP caster %s:%d ...", self._host, self._port)
        self._sock.connect((self._host, self._port))
        self._sock.sendall(self._build_ntrip_request())
        logger.info("NTRIP: GET /%s sent", self._mountpoint)

        first_chunk = self._sock.recv(4096)
        if not first_chunk:
            raise ConnectionError("NTRIP: empty initial response")

        if b"\r\n\r\n" in first_chunk:
            header, payload = first_chunk.split(b"\r\n\r\n", 1)
        elif b"\n\n" in first_chunk:
            header, payload = first_chunk.split(b"\n\n", 1)
        else:
            header, payload = first_chunk, b""

        header_text = header.decode(errors="ignore")[:200]
        logger.info("NTRIP response: %s", header_text.replace("\r", " ").replace("\n", " "))

        if b"200" not in header and b"ICY" not in header:
            raise ConnectionError(f"NTRIP rejected: {header_text}")

        logger.info("NTRIP connected, starting GGA + RTCM3 reception")

        # Start GGA sender thread
        gga_thread = threading.Thread(target=self._gga_sender_loop, daemon=True)
        gga_thread.start()

        if payload:
            self._write_serial(payload)

        while self._running:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError("NTRIP stream closed")
            self._write_serial(chunk)

    def _gga_sender_loop(self):
        """Periodically send GGA sentences on the NTRIP socket."""
        while self._running and self._sock:
            try:
                gga = build_gga(self._gga_lat, self._gga_lon, self._gga_alt)
                self._sock.sendall(gga)
                logger.debug("GGA sent: %s", gga.decode().strip())
            except Exception as exc:
                logger.debug("GGA send failed: %s", exc)
                break
            time.sleep(self._gga_interval)

    def _write_serial(self, data: bytes):
        """Write RTCM3 chunk to serial port (thread-safe)."""
        with self._ser_lock:
            try:
                self._ser.write(data)
                self._ser.flush()
            except Exception as exc:
                logger.debug("Serial write error: %s", exc)
                return
        self._total_bytes += len(data)
        self._total_frames += 1

        now = time.monotonic()
        if now - self._last_log >= 30.0:
            self._last_log = now
            logger.info(
                "NTRIP→Serial: %d frames, %.1f KB",
                self._total_frames, self._total_bytes / 1024,
            )


# ---------------------------------------------------------------------------
# Main positioning logic
# ---------------------------------------------------------------------------

class IchimillPositioner:
    """Main controller for the ichimill auto-positioning workflow."""

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
        fix_timeout: float = DEFAULT_FIX_TIMEOUT,
        collect_sec: float = DEFAULT_COLLECT_SEC,
        collect_interval: float = DEFAULT_COLLECT_INTERVAL,
    ):
        self.port = port
        self.baudrate = baudrate
        self.fix_timeout = fix_timeout
        self.collect_sec = collect_sec
        self.collect_interval = collect_interval
        self._ser: serial.Serial | None = None
        self._ntrip: NtripGgaClient | None = None
        self._shutdown = False

        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

    def _on_signal(self, signum, frame):
        logger.info("Signal %d received, shutting down...", signum)
        self._shutdown = True

    def _open_serial(self) -> serial.Serial:
        logger.info("Opening serial: %s @ %d bps", self.port, self.baudrate)
        ser = serial.Serial(self.port, self.baudrate, timeout=1.0)
        time.sleep(0.3)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        return ser

    def _close_serial(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
            self._ser = None

    def _send_ubx(self, data: bytes):
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial not open")
        self._ser.reset_input_buffer()
        self._ser.write(data)
        self._ser.flush()

    # ── CFG-VALSET steps ────────────────────────────────────────────────

    def _step_disable_tmode3(self) -> bool:
        """STEP 1: Disable TMODE3 (MODE=0)."""
        logger.info("STEP 1: Disabling TMODE3 (MODE=0) ...")
        try:
            cfg_data = [("CFG-TMODE-MODE", 0)]
            msg = build_cfg_valset(cfg_data, LAYER_RAM)
            self._send_ubx(msg)
            ack = read_ubx_response(self._ser, UBX_CLS_CFG, UBX_MID_ACK_ACK, timeout=2.0)
            if ack:
                logger.info("  ✓ TMODE3 disabled (ACK received)")
            else:
                logger.warning("  ⚠ No ACK for TMODE3 disable, proceeding anyway")
            return True
        except Exception as exc:
            logger.error("  ✗ TMODE3 disable failed: %s", exc)
            return False

    def _step_enable_rtcm3_input(self) -> bool:
        """STEP 2: Enable RTCM3 input on UART1 (key_id=0x40520004)."""
        logger.info("STEP 2: Enabling UART1 RTCM3 input (0x40520004) ...")
        try:
            cfg_data = [("CFG-UART1INPROT-RTCM3X", 1)]
            msg = build_cfg_valset(cfg_data, LAYER_RAM)
            self._send_ubx(msg)
            ack = read_ubx_response(self._ser, UBX_CLS_CFG, UBX_MID_ACK_ACK, timeout=2.0)
            if ack:
                logger.info("  ✓ RTCM3 input enabled (ACK received)")
            else:
                logger.warning("  ⚠ No ACK for RTCM3 input enable, proceeding anyway")
            return True
        except Exception as exc:
            logger.error("  ✗ RTCM3 input enable failed: %s", exc)
            return False

    def _poll_nav_pvt(self, timeout: float = 2.0) -> dict | None:
        """Poll UBX-NAV-PVT once, return parsed dict or None."""
        try:
            poll = build_nav_pvt_poll()
            self._send_ubx(poll)
        except Exception:
            return None
        raw = read_ubx_response(self._ser, UBX_CLS_NAV, UBX_MID_NAV_PVT, timeout=timeout)
        if raw is None:
            return None
        return parse_nav_pvt(raw)

    # ── Wait for FIX ────────────────────────────────────────────────────

    def _wait_for_fix(self) -> bool:
        """Poll NAV-PVT until fixType=6, carrSoln=2. Max ``fix_timeout`` sec."""
        logger.info("STEP 4: Waiting for RTK FIXED (max %.0fs) ...", self.fix_timeout)
        start = time.monotonic()
        deadline = start + self.fix_timeout
        last_status_log = start

        while time.monotonic() < deadline and not self._shutdown:
            pvt = self._poll_nav_pvt(timeout=2.0)
            now = time.monotonic()
            elapsed = now - start

            if pvt:
                ft = pvt["fix_type"]
                cs = pvt["carr_soln"]
                ft_name = FIX_TYPE_NAMES.get(ft, f"?{ft}")
                cs_name = CARR_SOLN_NAMES.get(cs, f"?{cs}")

                if now - last_status_log >= 5.0:
                    last_status_log = now
                    logger.info(
                        "  t=%5.1fs  fixType=%d(%s)  carrSoln=%d(%s)  sats=%d  "
                        "lat=%.7f lon=%.7f h=%.3fm  hAcc=%.3fm",
                        elapsed, ft, ft_name, cs, cs_name,
                        pvt["num_sv"], pvt["lat"], pvt["lon"],
                        pvt["height"], pvt["h_acc"],
                    )

                if ft == 6 and cs == 2:
                    logger.info(
                        "  ★ RTK FIXED achieved at t=%.1fs!  "
                        "lat=%.7f lon=%.7f h=%.3fm",
                        elapsed, pvt["lat"], pvt["lon"], pvt["height"],
                    )
                    return True
            else:
                if now - last_status_log >= 10.0:
                    last_status_log = now
                    logger.warning("  t=%5.1fs  No NAV-PVT response", elapsed)

            time.sleep(0.5)

        logger.error(
            "  ✗ RTK FIXED not achieved within %.0fs — aborting", self.fix_timeout
        )
        return False

    # ── Collect FIXED samples ──────────────────────────────────────────

    def _collect_fixed_samples(self) -> list[dict]:
        """Collect NAV-PVT samples for ``collect_sec`` sec.

        Only samples with carrSoln=2 are retained.
        """
        logger.info(
            "STEP 5: Collecting FIXED samples for %.0fs at %.1fs interval ...",
            self.collect_sec, self.collect_interval,
        )

        start = time.monotonic()
        deadline = start + self.collect_sec
        samples: list[dict] = []
        next_poll = start
        last_status_log = start

        while time.monotonic() < deadline and not self._shutdown:
            now = time.monotonic()
            if now < next_poll:
                time.sleep(0.05)
                continue
            next_poll = now + self.collect_interval

            pvt = self._poll_nav_pvt(timeout=1.5)
            if pvt is None:
                continue

            if pvt["carr_soln"] == 2:
                pvt["elapsed"] = now - start
                samples.append(pvt)

            if now - last_status_log >= 10.0:
                last_status_log = now
                logger.info(
                    "  t=%5.1fs  collected=%d  bytes_rcvd=%d",
                    now - start, len(samples),
                    self._ntrip.total_bytes if self._ntrip else 0,
                )

        logger.info(
            "Collection complete: %d FIXED samples in %.1fs",
            len(samples), time.monotonic() - start,
        )
        return samples

    # ── Statistics ─────────────────────────────────────────────────────

    @staticmethod
    def _compute_stats(samples: list[dict]) -> dict:
        """Compute mean and stddev of lat, lon, height."""
        if not samples:
            return {
                "lat_mean": 0, "lat_std_cm": 0, "lon_mean": 0,
                "lon_std_cm": 0, "h_mean": 0, "h_std_cm": 0, "n": 0,
            }

        lats = [s["lat"] for s in samples]
        lons = [s["lon"] for s in samples]
        heights = [s["height"] for s in samples]
        n = len(samples)

        lat_mean = statistics.mean(lats)
        lon_mean = statistics.mean(lons)
        h_mean = statistics.mean(heights)

        lat_std = statistics.stdev(lats) if n >= 2 else 0.0
        lon_std = statistics.stdev(lons) if n >= 2 else 0.0
        h_std = statistics.stdev(heights) if n >= 2 else 0.0

        lat_std_cm = lat_std * 111320.0 * 100
        lon_std_cm = lon_std * 111320.0 * math.cos(math.radians(lat_mean)) * 100
        h_std_cm = h_std * 100

        return {
            "lat_mean": lat_mean, "lat_std_cm": lat_std_cm,
            "lon_mean": lon_mean, "lon_std_cm": lon_std_cm,
            "h_mean": h_mean, "h_std_cm": h_std_cm, "n": n,
        }

    # ── Update base_station.json ────────────────────────────────────────

    def _update_base_station_json(self, lat: float, lon: float, alt: float):
        """Update config/base_station.json with the averaged coordinates."""
        project_root = Path(__file__).parent.parent
        path = project_root / BASE_STATION_JSON
        logger.info("STEP 6: Updating %s ...", path)

        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass

        existing["mode"] = "ichimill_auto"
        existing["fixed_lat"] = lat
        existing["fixed_lon"] = lon
        existing["fixed_alt"] = alt
        existing["serial_port"] = self.port
        existing["baudrate"] = self.baudrate
        existing["save_to_flash"] = True
        existing["auto_positioned_at"] = datetime.now().isoformat()

        path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info(
            "  ✓ Updated: lat=%.7f lon=%.7f alt=%.3f", lat, lon, alt
        )

    # ── Write TMODE3 FIXED ─────────────────────────────────────────────

    def _write_tmode3_fixed(self, lat: float, lon: float, alt: float) -> bool:
        """STEP 7: Write TMODE3 MODE=2 (FIXED) with the averaged position."""
        logger.info("STEP 7: Writing TMODE3 FIXED mode ...")
        lat_e7 = int(lat * 1e7)
        lon_e7 = int(lon * 1e7)
        alt_cm = int(alt * 100)

        try:
            cfg_data = [
                ("CFG-TMODE-MODE", 2),
                ("CFG-TMODE-POS_TYPE", 0),
                ("CFG-TMODE-LAT", lat_e7),
                ("CFG-TMODE-LON", lon_e7),
                ("CFG-TMODE-HEIGHT", alt_cm),
            ]
            msg = build_cfg_valset(cfg_data, LAYER_ALL)
            self._send_ubx(msg)
            time.sleep(0.5)

            ack = read_ubx_response(
                self._ser, UBX_CLS_CFG, UBX_MID_ACK_ACK, timeout=3.0
            )
            if ack:
                logger.info(
                    "  ✓ TMODE3 FIXED written to Flash: "
                    "lat=%.7f lon=%.7f h=%.3fm", lat, lon, alt
                )
            else:
                logger.warning("  ⚠ No ACK for TMODE3 FIXED write")
            return True
        except Exception as exc:
            logger.error("  ✗ TMODE3 FIXED write failed: %s", exc)
            return False

    # ── Run ─────────────────────────────────────────────────────────────

    def run(self) -> dict:
        """Execute the full auto-positioning workflow."""
        logger.info("=" * 60)
        logger.info("  イチミルNTRIP基地局 全自動測位")
        logger.info("  Port: %s @ %d bps", self.port, self.baudrate)
        logger.info(
            "  Fix timeout: %.0fs  |  Collect: %.0fs",
            self.fix_timeout, self.collect_sec,
        )
        logger.info("=" * 60)

        result = {"success": False, "lat": None, "lon": None, "alt": None}

        # ── Open serial ──
        try:
            self._ser = self._open_serial()
        except Exception as exc:
            logger.error("Failed to open serial: %s", exc)
            return result

        try:
            if not self._step_disable_tmode3():
                return result
            time.sleep(0.3)

            if not self._step_enable_rtcm3_input():
                return result
            time.sleep(0.3)

            logger.info("STEP 3: Starting NTRIP + GGA client ...")
            self._ntrip = NtripGgaClient(serial_port=self._ser)
            self._ntrip.start()
            time.sleep(2.0)

            if not self._wait_for_fix():
                return result

            samples = self._collect_fixed_samples()
            if not samples:
                logger.error("No FIXED samples collected — aborting")
                return result

            stats = self._compute_stats(samples)
            logger.info("")
            logger.info("=" * 60)
            logger.info("  STATISTICS (%d FIXED samples)", stats["n"])
            logger.info(
                "  Lat  Mean: %.8f   StdDev: %.3f cm",
                stats["lat_mean"], stats["lat_std_cm"],
            )
            logger.info(
                "  Lon  Mean: %.8f   StdDev: %.3f cm",
                stats["lon_mean"], stats["lon_std_cm"],
            )
            logger.info(
                "  Hgt  Mean: %.4f m   StdDev: %.3f cm",
                stats["h_mean"], stats["h_std_cm"],
            )
            logger.info("=" * 60)

            self._update_base_station_json(
                stats["lat_mean"], stats["lon_mean"], stats["h_mean"]
            )

            if not self._write_tmode3_fixed(
                stats["lat_mean"], stats["lon_mean"], stats["h_mean"]
            ):
                return result

            result["success"] = True
            result["lat"] = stats["lat_mean"]
            result["lon"] = stats["lon_mean"]
            result["alt"] = stats["h_mean"]
            result["stats"] = stats

        finally:
            if self._ntrip:
                self._ntrip.stop()
            self._close_serial()

        if result["success"]:
            logger.info("")
            logger.info("=" * 60)
            logger.info("  ★ AUTO-POSITIONING COMPLETE ★")
            logger.info(
                "  Base: lat=%.8f lon=%.8f h=%.4fm",
                result["lat"], result["lon"], result["alt"],
            )
            logger.info("  TMODE3=FIXED written to Flash")
            logger.info("  base_station.json updated")
            logger.info("=" * 60)

        return result


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="イチミルNTRIP基地局 全自動測位スクリプト",
    )
    parser.add_argument(
        "--port", default=DEFAULT_PORT,
        help=f"Serial port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--baudrate", type=int, default=DEFAULT_BAUDRATE,
        help=f"Baudrate (default: {DEFAULT_BAUDRATE})",
    )
    parser.add_argument(
        "--fix-timeout", type=float, default=DEFAULT_FIX_TIMEOUT,
        help=f"Max seconds for FIX wait (default: {DEFAULT_FIX_TIMEOUT})",
    )
    parser.add_argument(
        "--collect-sec", type=float, default=DEFAULT_COLLECT_SEC,
        help=f"Collection duration (default: {DEFAULT_COLLECT_SEC})",
    )
    parser.add_argument(
        "--collect-interval", type=float, default=DEFAULT_COLLECT_INTERVAL,
        help=f"Poll interval (default: {DEFAULT_COLLECT_INTERVAL})",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    positioner = IchimillPositioner(
        port=args.port,
        baudrate=args.baudrate,
        fix_timeout=args.fix_timeout,
        collect_sec=args.collect_sec,
        collect_interval=args.collect_interval,
    )

    result = positioner.run()
    if result["success"]:
        print(
            f"\nFinal position: "
            f"lat={result['lat']:.8f} lon={result['lon']:.8f} alt={result['alt']:.4f}m"
        )
        return 0
    else:
        print("\nPositioning failed. Check logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
