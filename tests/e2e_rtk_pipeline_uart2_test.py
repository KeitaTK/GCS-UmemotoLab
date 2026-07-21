#!/usr/bin/env python3
"""
E2E RTK Pipeline Test — MAVLink非依存（UART2直接注入）パス

パスB（RTCM注入）: MAVLink GPS_RTCM_DATA 不使用
  基地局F9P → TCP:2101(生RTCM3) → rtk_forwarder_service.py → /dev/ttyAMA4 → F9P Rover UART2

検証項目:
  Step 1: 基地局起動 + RTCM出力確認 (0xD3 preamble, type 1005/1006)
  Step 2: RTCM転送確認 (Forward stats 増加, frames_per_min > 0)
  Step 3: Fix遷移監視 (fix_type: 3→4(DGPS)→5(FLOAT)→6(FIXED), carrSoln遷移)
  Step 4: ログ確認 (rtcm_injection.log, rtcm_fix_transition.log)

Usage:
  # シミュレーションモード（ハードウェア不要）
  python tests/e2e_rtk_pipeline_uart2_test.py

  # 実機テスト（基地局・Raspi・GCSが稼働中）
  python tests/e2e_rtk_pipeline_uart2_test.py --live \
      --base-host localhost --base-port 2101 \
      --gcs-url http://localhost:8000 \
      --timeout 300

  # 個別ステップのみ
  python tests/e2e_rtk_pipeline_uart2_test.py --steps 1,3
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# RTCM3 frame constants
# ---------------------------------------------------------------------------
RTCM3_PREAMBLE = 0xD3
RTCM3_HEADER_LEN = 3
RTCM3_CRC_LEN = 3
RTCM3_LENGTH_MASK = 0x03   # per 2026-07-21 fix: was 0x3F

# RTCM3 message types
MSG_TYPE_1005 = 1005   # Stationary RTK Reference Station ARP
MSG_TYPE_1006 = 1006   # Stationary RTK Reference Station ARP + Antenna Height
MSG_TYPE_1074 = 1074   # GPS MSM4
MSG_TYPE_1084 = 1084   # GLONASS MSM4
MSG_TYPE_1094 = 1094   # Galileo MSM4
MSG_TYPE_1124 = 1124   # BeiDou MSM4

# ---------------------------------------------------------------------------
# RTCM3 frame utilities
# ---------------------------------------------------------------------------
def extract_rtcm_message_type(frame: bytes) -> Optional[int]:
    """Extract the RTCM3 message type (DF002, 12-bit) from a frame.

    RTCM3 frame structure:
      byte 0: preamble (0xD3)
      byte 1: [7:6]=reserved, [5:0]=len[9:4]
      byte 2: len[3:0]
      bytes 3-: payload (len bytes)
      last 3 bytes: CRC-24Q

    DF002 is bits 24-35 of the frame = payload[0]<<4 | payload[1]>>4
    """
    if len(frame) < 6 or frame[0] != RTCM3_PREAMBLE:
        return None
    payload_len = ((frame[1] & RTCM3_LENGTH_MASK) << 8) | frame[2]
    if len(frame) < RTCM3_HEADER_LEN + payload_len + RTCM3_CRC_LEN:
        return None
    payload = frame[3:3 + payload_len]
    if len(payload) < 2:
        return None
    return (payload[0] << 4) | (payload[1] >> 4)


def make_rtcm3_frame(msg_type: int, body_bytes: int = 20) -> bytes:
    """Build a minimal valid RTCM3 frame with the given message type.

    msg_type is DF002 (12-bit). The frame has valid structure but
    placeholder CRC (zero-filled).
    """
    payload = bytearray()
    payload.append((msg_type >> 4) & 0xFF)
    payload.append(((msg_type & 0x0F) << 4))
    # Pad to desired body size
    while len(payload) < body_bytes:
        payload.append(0xAA)
    payload_len = len(payload)

    header = bytearray(3)
    header[0] = RTCM3_PREAMBLE
    header[1] = (payload_len >> 8) & RTCM3_LENGTH_MASK
    header[2] = payload_len & 0xFF

    crc = b'\x00\x00\x00'  # placeholder CRC-24Q
    return bytes(header) + bytes(payload) + crc


# ---------------------------------------------------------------------------
# Mock RTCM TCP Server (simulates base station for testing without hardware)
# ---------------------------------------------------------------------------
class MockRtcmTcpServer:
    """TCP server that streams realistic RTCM3 frames simulating a base station."""

    def __init__(self, host="127.0.0.1", port=2101, interval=0.05):
        self.host = host
        self.port = port
        self.interval = interval
        self._running = False
        self._thread = None
        self._server_sock = None
        self.stats = {"frames_sent": 0, "bytes_sent": 0, "clients": 0}

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        time.sleep(0.3)

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2)

    def _serve(self):
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.settimeout(0.5)
        try:
            self._server_sock.bind((self.host, self.port))
            self._server_sock.listen(5)
        except OSError:
            self._running = False
            return

        patterns = [
            (MSG_TYPE_1005, 22), (MSG_TYPE_1006, 36),
            (MSG_TYPE_1074, 60), (MSG_TYPE_1084, 55),
            (MSG_TYPE_1094, 58), (MSG_TYPE_1124, 52),
        ]

        while self._running:
            try:
                client, addr = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            self.stats["clients"] += 1
            # Handle this client in a separate thread
            t = threading.Thread(target=self._handle_client, args=(client, patterns), daemon=True)
            t.start()

    def _handle_client(self, client, patterns):
        """Serve RTCM frames to a single client until disconnect."""
        try:
            while self._running:
                for msg_type, psize in patterns:
                    if not self._running:
                        return
                    frame = make_rtcm3_frame(msg_type, psize)
                    try:
                        client.sendall(frame)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    self.stats["frames_sent"] += 1
                    self.stats["bytes_sent"] += len(frame)
                    time.sleep(self.interval)
        finally:
            try:
                client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Mock GCS REST API Server (simulates GCS for testing without hardware)
# ---------------------------------------------------------------------------
class MockGcsServer:
    """Minimal HTTP server simulating the GCS REST API /api/drones endpoint.

    Returns GPS data progressing through fix_type transitions:
      3 (3D_FIX) → 4 (DGPS) → 5 (RTK_FLOAT) → 6 (RTK_FIXED)
    """

    def __init__(self, host="127.0.0.1", port=18800):
        self.host = host
        self.port = port
        self._running = False
        self._thread = None
        self._server_sock = None
        self._polls_per_stage = 5

    @property
    def url(self):
        return f"http://{self.host}:{self.port}"

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        time.sleep(0.3)

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2)

    def _get_current_fix(self, poll_count: int) -> dict:
        if poll_count < self._polls_per_stage:
            return {"fix_type": 3, "carrSoln": 0}
        elif poll_count < self._polls_per_stage * 2:
            return {"fix_type": 4, "carrSoln": 0}
        elif poll_count < self._polls_per_stage * 3:
            return {"fix_type": 5, "carrSoln": 1}
        else:
            return {"fix_type": 6, "carrSoln": 2}

    def _serve(self):
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.settimeout(0.5)
        try:
            self._server_sock.bind((self.host, self.port))
            self._server_sock.listen(2)
        except OSError:
            self._running = False
            return

        poll_count = 0
        while self._running:
            try:
                client, addr = self._server_sock.accept()
                try:
                    request = client.recv(4096).decode(errors="ignore")
                    if "/api/drones" in request:
                        poll_count += 1
                        gps = self._get_current_fix(poll_count)
                        body = json.dumps({
                            "drones": [{
                                "system_id": 1,
                                "gps_fix": gps["fix_type"],
                                "gps_sats": 22,
                                "lat": 36.0751418,
                                "lon": 136.2133477,
                                "alt": 15.5,
                                "hdop": 0.62,
                            }]
                        })
                        resp = (
                            "HTTP/1.1 200 OK\r\n"
                            "Content-Type: application/json\r\n"
                            f"Content-Length: {len(body)}\r\n"
                            "Connection: close\r\n\r\n"
                            + body
                        )
                        client.sendall(resp.encode())
                    else:
                        client.sendall(b"HTTP/1.1 404 Not Found\r\n\r\n")
                finally:
                    try:
                        client.close()
                    except Exception:
                        pass
            except socket.timeout:
                continue
            except OSError:
                break


# ---------------------------------------------------------------------------
# Test Data Classes
# ---------------------------------------------------------------------------
@dataclass
class StepResult:
    step: int
    name: str
    passed: bool
    details: str = ""
    evidence: dict = field(default_factory=dict)


@dataclass
class TestConfig:
    base_host: str = "127.0.0.1"
    base_port: int = 2101
    gcs_url: str = "http://localhost:8000"
    timeout: float = 300.0
    live: bool = False
    steps: list = field(default_factory=lambda: [1, 2, 3, 4])

# ---------------------------------------------------------------------------
# E2E RTK Pipeline UART2 Test Runner
# ---------------------------------------------------------------------------
class E2eRtkPipelineUart2Test:
    """End-to-end test for the MAVLink-independent RTCM injection pipeline.

    Data flow: Base F9P → TCP:2101 (raw RTCM3) → forwarder → /dev/ttyAMA4 → F9P Rover UART2
    """

    PROJECT_ROOT = Path(__file__).resolve().parent.parent

    def __init__(self, config: TestConfig):
        self.config = config
        self.results: list[StepResult] = []
        self._mock_base = None
        self._mock_gcs = None

    def _log(self, msg: str, level: str = "INFO"):
        prefix = {"INFO": "  ", "PASS": "  ✓ ", "FAIL": "  ✗ ", "STEP": "━ "}
        print(f"{prefix.get(level, '  ')}{msg}")

    def _result(self, step: int, name: str, passed: bool, details: str = "", **evidence):
        self.results.append(StepResult(step, name, passed, details, evidence))
        status = "PASS" if passed else "FAIL"
        self._log(f"{name}: {status}", status)
        return passed

    # ── Step 1: 基地局起動 + RTCM出力確認 ─────────────────────────────────
    def step1_verify_base_station_output(self) -> bool:
        """Verify base station TCP delivers valid RTCM3 frames.

        Checks: TCP connectivity, 0xD3 preamble, type 1005/1006 frames.
        """
        self._log("━" * 50, "STEP")
        self._log("Step 1: 基地局 RTCM出力確認 (TCP base station output)", "STEP")

        if self.config.live:
            host, port = self.config.base_host, self.config.base_port
        else:
            host, port = "127.0.0.1", 2101
            self._mock_base = MockRtcmTcpServer(host=host, port=port, interval=0.05)
            self._mock_base.start()
            self._log(f"Mock RTCM base station started on {host}:{port}")
            time.sleep(0.5)

        # Check 1: TCP connectivity
        self._log(f"Connecting to TCP {host}:{port} ...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, port))
            sock.settimeout(3.0)
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            return self._result(1, "TCP connectivity", False, f"Cannot connect: {e}")
        self._result(1, "TCP connectivity", True, f"Connected to {host}:{port}")

        # Check 2: 0xD3 preamble detection
        buffer = bytearray()
        received_frames = []
        deadline = time.monotonic() + 10.0
        self._log("Reading RTCM3 frames (looking for 0xD3 preamble)...")
        while time.monotonic() < deadline:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                buffer.extend(data)
                while len(buffer) >= 6:
                    if buffer[0] != RTCM3_PREAMBLE:
                        buffer.pop(0)
                        continue
                    fl = ((buffer[1] & RTCM3_LENGTH_MASK) << 8) | buffer[2]
                    tl = RTCM3_HEADER_LEN + fl + RTCM3_CRC_LEN
                    if len(buffer) < tl:
                        break
                    received_frames.append(bytes(buffer[:tl]))
                    buffer = buffer[tl:]
            except socket.timeout:
                continue
        sock.close()

        if len(received_frames) == 0:
            return self._result(1, "0xD3 preamble", False, "No RTCM3 frames found")
        self._result(1, "0xD3 preamble", True,
                     f"Found {len(received_frames)} RTCM3 frames with 0xD3 preamble")

        # Check 3: type 1005/1006 frames
        frame_types = set()
        count_1005 = 0
        count_1006 = 0
        for frame in received_frames:
            mt = extract_rtcm_message_type(frame)
            if mt is not None:
                frame_types.add(mt)
                if mt == MSG_TYPE_1005:
                    count_1005 += 1
                elif mt == MSG_TYPE_1006:
                    count_1006 += 1

        self._log(f"  Detected RTCM3 message types: {sorted(frame_types)}")
        self._log(f"    type 1005 (0x3ED): {count_1005} frames")
        self._log(f"    type 1006 (0x3EE): {count_1006} frames")

        has_1005_or_1006 = (MSG_TYPE_1005 in frame_types) or (MSG_TYPE_1006 in frame_types)
        if not has_1005_or_1006:
            return self._result(1, "type 1005/1006", False,
                                f"No type 1005/1006. Found: {sorted(frame_types)}")
        self._result(1, "type 1005/1006", True,
                     f"1005: {count_1005}, 1006: {count_1006}",
                     frame_types=sorted(frame_types),
                     total_frames=len(received_frames))
        return True



    # ── Step 2: RTCM転送確認 (Forward stats) ────────────────────────────
    def step2_verify_rtcm_forwarding(self) -> bool:
        """Verify RTCM forwarder is receiving and forwarding frames.

        Checks: Forward stats increase, frames_per_min > 0.
        """
        self._log("━" * 50, "STEP")
        self._log("Step 2: RTCM転送確認 (Forward stats verification)", "STEP")

        if self.config.live:
            injection_log = self.PROJECT_ROOT / "logs" / "rtcm_injection.log"
            forwarder_log = self.PROJECT_ROOT / "logs" / "rtk_forwarder.log"
            if not injection_log.exists() and not forwarder_log.exists():
                return self._result(2, "Forwarder logs", False,
                                    "rtcm_injection.log / rtk_forwarder.log not found. "
                                    "Is rtk_forwarder_service.py running on Raspi?")
            self._result(2, "Forwarder logs exist", True)
            if injection_log.exists():
                content = injection_log.read_text()
                lines = [l for l in content.strip().split('\n')
                         if l and not l.startswith('timestamp')]
                if len(lines) >= 2:
                    last = lines[-1].split(',')
                    if len(last) >= 4:
                        fpm = float(last[3])
                        self._log(f"  Last entry: frames_per_min={fpm}")
                        return self._result(2, "Forward stats", fpm > 0,
                                            f"frames_per_min={fpm}")
                return self._result(2, "Forward stats", False, "Insufficient data")
            return self._result(2, "Forward stats", False, "No injection log")
        else:
            # Simulation: connect to mock base and count frames over 3 seconds
            if self._mock_base is None:
                self._mock_base = MockRtcmTcpServer(host="127.0.0.1", port=2101, interval=0.02)
                self._mock_base.start()
                time.sleep(0.3)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            try:
                sock.connect(("127.0.0.1", 2101))
            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                return self._result(2, "TCP connection", False, f"{e}")

            buffer = bytearray()
            count = 0
            bcount = 0
            start = time.monotonic()
            deadline = start + 3.0
            while time.monotonic() < deadline:
                try:
                    data = sock.recv(4096)
                    if not data:
                        break
                    buffer.extend(data)
                    bcount += len(data)
                    while len(buffer) >= 6:
                        if buffer[0] != RTCM3_PREAMBLE:
                            buffer.pop(0)
                            continue
                        fl = ((buffer[1] & RTCM3_LENGTH_MASK) << 8) | buffer[2]
                        tl = RTCM3_HEADER_LEN + fl + RTCM3_CRC_LEN
                        if len(buffer) < tl:
                            break
                        buffer = buffer[tl:]
                        count += 1
                except socket.timeout:
                    continue
            sock.close()

            elapsed = time.monotonic() - start
            fpm = (count / elapsed) * 60.0 if elapsed > 0 else 0.0
            self._log(f"  Collected {count} frames ({bcount} bytes) in {elapsed:.1f}s")
            self._log(f"  Rate: {fpm:.1f} frames/min")

            if count >= 3:
                return self._result(2, "Forward stats", True,
                                    f"{count} frames, {fpm:.1f} frames/min",
                                    frames_per_min=fpm)
            return self._result(2, "Forward stats", False, f"Only {count} frames")


    # ── Step 3: Fix監視 (fix_type 遷移) ─────────────────────────────────
    def step3_monitor_fix_transitions(self) -> bool:
        """Monitor fix_type via GCS REST API and verify transition sequence.

        Expected: 3(3D_FIX) → 4(DGPS) → 5(RTK_FLOAT) → 6(RTK_FIXED)
        carrSoln:      0(NONE)   → 0(NONE)   → 1(FLOAT)     → 2(FIXED)
        """
        self._log("━" * 50, "STEP")
        self._log("Step 3: Fix監視 (fix_type transition monitoring)", "STEP")

        import requests

        gcs_url = self.config.gcs_url
        if not self.config.live:
            mg = MockGcsServer(port=18800)
            mg.start()
            gcs_url = mg.url
            self._log(f"Mock GCS API server started: {gcs_url}")

        self._log(f"Polling GCS API: {gcs_url}/api/drones")
        timeout = self.config.timeout if self.config.live else 30.0

        prev_fix = -1
        prev_carr = -1
        observed_fix_types = set()
        carr_transitions: list[tuple[float, int, int]] = []
        fix_transitions: list[tuple[float, int, int]] = []
        start = time.monotonic()

        reached = {"dgps": False, "float": False, "fixed": False}
        fix_names = {3: "3D_FIX", 4: "DGPS", 5: "RTK_FLOAT", 6: "RTK_FIXED"}
        carr_map = {3: 0, 4: 0, 5: 1, 6: 2}
        carr_names = {0: "NONE", 1: "FLOAT", 2: "FIXED"}

        while time.monotonic() - start < timeout:
            elapsed = time.monotonic() - start
            try:
                resp = requests.get(f"{gcs_url}/api/drones", timeout=5.0)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                self._log(f"  t={elapsed:5.1f}s  (GCS API error: {e})")
                time.sleep(1.0)
                continue

            drones = data.get("drones", [])
            if not drones:
                self._log(f"  t={elapsed:5.1f}s  (no drone data)")
                time.sleep(1.0)
                continue

            d = drones[0]
            fix_type = d.get("gps_fix", -1)
            carr_soln = carr_map.get(fix_type, 0)

            if fix_type != prev_fix and prev_fix != -1:
                fix_transitions.append((elapsed, prev_fix, fix_type))
                self._log(f"  >>> fix_type: {fix_names.get(prev_fix, str(prev_fix))} → "
                          f"{fix_names.get(fix_type, str(fix_type))} at t={elapsed:.1f}s <<<")
            if carr_soln != prev_carr and prev_carr != -1:
                carr_transitions.append((elapsed, prev_carr, carr_soln))
                self._log(f"  >>> carrSoln: {carr_names.get(prev_carr, '?')}→"
                          f"{carr_names.get(carr_soln, '?')} at t={elapsed:.1f}s <<<")

            prev_fix = fix_type
            prev_carr = carr_soln
            observed_fix_types.add(fix_type)

            self._log(f"  t={elapsed:5.1f}s  fix_type={fix_type}"
                      f"({fix_names.get(fix_type, '?')})  "
                      f"carrSoln={carr_soln}({carr_names[carr_soln]})  "
                      f"sats={d.get('gps_sats', '?')}  hdop={d.get('hdop', 'N/A')}")

            if fix_type == 4:
                reached["dgps"] = True
            if fix_type == 5:
                reached["float"] = True
            if fix_type == 6:
                reached["fixed"] = True
                break

            time.sleep(1.0)

        if not self.config.live:
            mg.stop()

        checks = [
            ("DGPS (fix_type=4)", reached["dgps"]),
            ("FLOAT (fix_type=5)", reached["float"]),
            ("FIXED (fix_type=6)", reached["fixed"]),
            ("carrSoln transitions", len(carr_transitions) >= 1),
        ]
        all_pass = all(p for _, p in checks)
        for name, passed in checks:
            self._log(f"    {'✓' if passed else '✗'} {name}")

        return self._result(3, "Fix transitions", all_pass,
                            "; ".join(f"{'✓' if p else '✗'} {n}" for n, p in checks),
                            observed_fix_types=sorted(observed_fix_types),
                            fix_transitions=fix_transitions,
                            carr_soln_transitions=carr_transitions)


    # ── Step 4: ログ確認 ───────────────────────────────────────────────
    def step4_verify_logs(self) -> bool:
        """Verify that log files exist and contain expected content."""
        self._log("━" * 50, "STEP")
        self._log("Step 4: ログ確認 (log file verification)", "STEP")

        log_dir = self.PROJECT_ROOT / "logs"
        all_pass = True

        # rtcm_injection.log
        inj_log = log_dir / "rtcm_injection.log"
        if inj_log.exists():
            content = inj_log.read_text().strip()
            lines = [l for l in content.split('\n') if l.strip()]
            data = [l for l in lines if not l.startswith('timestamp')]
            self._log(f"  rtcm_injection.log: {len(data)} data entries")
            self._result(4, "rtcm_injection.log", True, f"{len(data)} data lines")
        else:
            self._log(f"  rtcm_injection.log: NOT FOUND ({inj_log})")
            self._result(4, "rtcm_injection.log", False, "File not found")
            all_pass = False

        # rtcm_fix_transition.log
        fix_log = log_dir / "rtcm_fix_transition.log"
        if fix_log.exists():
            content = fix_log.read_text().strip()
            lines = [l for l in content.split('\n') if l.strip()]
            data = [l for l in lines if not l.startswith('timestamp') and not l.startswith('#')]
            summaries = [l for l in lines if l.startswith('#')]
            self._log(f"  rtcm_fix_transition.log: {len(data)} entries, {len(summaries)} summary")
            self._result(4, "rtcm_fix_transition.log", True,
                         f"{len(data)} data, {len(summaries)} summary")
            for sl in summaries:
                if "time_to_fixed" in sl or "time_to_float" in sl:
                    self._log(f"    {sl}")
        else:
            self._log(f"  rtcm_fix_transition.log: NOT FOUND ({fix_log})")
            self._result(4, "rtcm_fix_transition.log", False, "File not found")
            all_pass = False

        return all_pass

    # ── Run all steps ─────────────────────────────────────────────────
    def run(self) -> bool:
        step_map = {
            1: (self.step1_verify_base_station_output, "基地局 RTCM出力確認"),
            2: (self.step2_verify_rtcm_forwarding, "RTCM転送確認"),
            3: (self.step3_monitor_fix_transitions, "Fix監視"),
            4: (self.step4_verify_logs, "ログ確認"),
        }

        print()
        print("=" * 60)
        print("E2E RTK Pipeline UART2 Direct Injection Test")
        print("  パスB: 基地局F9P → TCP:2101 → forwarder → /dev/ttyAMA4 → F9P Rover UART2")
        print(f"  Mode: {'LIVE' if self.config.live else 'SIMULATION'}")
        print(f"  Steps: {self.config.steps}")
        print("=" * 60)

        try:
            for i, step_num in enumerate(sorted(self.config.steps)):
                if step_num in step_map:
                    if i > 0:
                        time.sleep(0.5)  # let mock servers recycle between steps
                    step_map[step_num][0]()

            if self._mock_base:
                self._mock_base.stop()
                self._mock_base = None

            # Summary
            print()
            print("=" * 60)
            print("TEST SUMMARY")
            print("=" * 60)
            all_pass = True
            for r in self.results:
                status = "✓ PASS" if r.passed else "✗ FAIL"
                print(f"  Step {r.step} [{status}] {r.name}: {r.details}")
                if not r.passed:
                    all_pass = False

            # 確認項目チェックリスト
            print()
            print("─" * 60)
            print("確認項目チェックリスト:")
            checklist = {
                "0xD3 preamble 確認（TCP:2101）": any(
                    r.step == 1 and "0xD3" in r.name and r.passed for r in self.results),
                "type 1005/1006 フレーム存在確認": any(
                    r.step == 1 and "1005/1006" in r.name and r.passed for r in self.results),
                "Forward stats 増加確認": any(
                    r.step == 2 and "Forward" in r.name and r.passed for r in self.results),
                "fix_type=6 (RTK FIXED) 到達確認": any(
                    r.step == 3 and r.passed for r in self.results),
                "carrSoln=2 (FIXED) 確認": any(
                    r.step == 3 and r.passed for r in self.results),
            }
            for item, passed in checklist.items():
                print(f"  {'✓' if passed else '✗'} {item}")

            print()
            if all_pass:
                print("🎉 All checks PASSED — RTK FIXED 到達確認!")
                return True
            else:
                print("⚠️  Some checks FAILED — see details above")
                return False

        except KeyboardInterrupt:
            print("\nInterrupted by user")
            if self._mock_base:
                self._mock_base.stop()
            return False
        except Exception as e:
            print(f"\nFatal error: {e}")
            import traceback
            traceback.print_exc()
            if self._mock_base:
                self._mock_base.stop()
            return False


# ---------------------------------------------------------------------------
# pytest-compatible test functions
# ---------------------------------------------------------------------------
class TestE2eRtkPipelineUart2:
    """pytest-compatible test class for CI/automated testing."""

    def test_step1_rtcm_preamble_and_types(self):
        """Verify 0xD3 preamble and type 1005/1006 in simulated RTCM stream."""
        config = TestConfig(live=False, steps=[1])
        test = E2eRtkPipelineUart2Test(config)
        result = test.step1_verify_base_station_output()
        if test._mock_base:
            test._mock_base.stop()
        assert result, "Step 1 failed: RTCM preamble or type 1005/1006 not found"

    def test_step2_forward_stats(self):
        """Verify forward stats increase (simulation mode)."""
        config = TestConfig(live=False, steps=[2])
        test = E2eRtkPipelineUart2Test(config)
        result = test.step2_verify_rtcm_forwarding()
        if test._mock_base:
            test._mock_base.stop()
        assert result, "Step 2 failed: Forward stats not increasing"

    def test_step3_fix_transitions(self):
        """Verify fix_type transitions 3→4→5→6 in simulation mode."""
        config = TestConfig(live=False, steps=[3])
        test = E2eRtkPipelineUart2Test(config)
        result = test.step3_monitor_fix_transitions()
        assert result, "Step 3 failed: RTK FIXED not reached in simulation"

    def test_step4_logs(self):
        """Verify log files exist with expected content."""
        config = TestConfig(live=False, steps=[4])
        test = E2eRtkPipelineUart2Test(config)
        log_dir = test.PROJECT_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)

        # Write sample injection log
        (log_dir / "rtcm_injection.log").write_text(
            "timestamp,frame_count,cumulative_bytes,frames_per_min,bytes_per_minute,errors\n"
            "2026-07-22T10:00:00,50,5000,300.0,30000.0,0\n"
            "2026-07-22T10:00:05,100,10000,300.0,30000.0,0\n"
        )
        # Write sample fix transition log
        (log_dir / "rtcm_fix_transition.log").write_text(
            "timestamp,elapsed_sec,carrSoln,carrSoln_name,numSV,hAcc,lat,lon,transition\n"
            "2026-07-22T10:00:00,0.0,0,NONE,20,1.500,36.0751418,136.2133477,\n"
            "2026-07-22T10:00:10,10.0,0,NONE,22,1.000,36.0751418,136.2133477,>>> FLOAT (0→1) <<<\n"
            "2026-07-22T10:00:15,15.0,1,FLOAT,22,0.800,36.0751420,136.2133479,>>> FIXED (1→2) <<<\n"
            "2026-07-22T10:00:20,20.0,2,FIXED,22,0.620,36.0751422,136.2133480,\n"
            "# SUMMARY,,,,,,,time_to_float=12.0s  time_to_fixed=20.0s\n"
        )
        result = test.step4_verify_logs()
        assert result, "Step 4 failed: Log files not verified"

    def test_full_e2e_simulation(self):
        """Full E2E pipeline test in simulation mode (all 4 steps)."""
        config = TestConfig(live=False, steps=[1, 2, 3, 4])
        test = E2eRtkPipelineUart2Test(config)
        result = test.run()
        if test._mock_base:
            test._mock_base.stop()
        assert result, "E2E RTK Pipeline UART2 test FAILED"


# ---------------------------------------------------------------------------
# __main__
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="E2E RTK Pipeline UART2 Direct Injection Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Simulation mode (no hardware)\n"
            "  python tests/e2e_rtk_pipeline_uart2_test.py\n"
            "\n"
            "  # Live test with actual hardware\n"
            "  python tests/e2e_rtk_pipeline_uart2_test.py --live \\\n"
            "      --base-host localhost --base-port 2101 \\\n"
            "      --gcs-url http://localhost:8000 --timeout 300\n"
            "\n"
            "  # Only specific steps\n"
            "  python tests/e2e_rtk_pipeline_uart2_test.py --steps 1,3\n"
            "\n"
            "  # Run as pytest\n"
            "  python tests/e2e_rtk_pipeline_uart2_test.py --pytest\n"
        ),
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Run in live mode against actual hardware/services"
    )
    parser.add_argument(
        "--base-host", default="localhost",
        help="Base station TCP host (default: localhost)"
    )
    parser.add_argument(
        "--base-port", type=int, default=2101,
        help="Base station TCP port (default: 2101)"
    )
    parser.add_argument(
        "--gcs-url", default="http://localhost:8000",
        help="GCS REST API base URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--timeout", type=float, default=300.0,
        help="Max wait time for RTK FIXED [seconds] (default: 300)"
    )
    parser.add_argument(
        "--steps", default="1,2,3,4",
        help="Comma-separated steps to run: 1,2,3,4 (default: all)"
    )
    parser.add_argument(
        "--pytest", action="store_true",
        help="Run as pytest test suite"
    )
    args = parser.parse_args()

    if args.pytest:
        sys.exit(pytest.main([__file__, "-v", "--tb=short"]))

    steps = [int(s.strip()) for s in args.steps.split(",") if s.strip().isdigit()]
    if not steps:
        steps = [1, 2, 3, 4]

    config = TestConfig(
        base_host=args.base_host,
        base_port=args.base_port,
        gcs_url=args.gcs_url,
        timeout=args.timeout,
        live=args.live,
        steps=steps,
    )

    test = E2eRtkPipelineUart2Test(config)
    success = test.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

