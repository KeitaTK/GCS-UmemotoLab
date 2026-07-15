#!/usr/bin/env python3
"""
rtk_direct_inject.py - RTCM UART2直接注入 + RTK Fix確認 自動化

5-STEP automated workflow:
  STEP 1: Configure Rover F9P UART2 (RTCM3 input + UBX output)
  STEP 2: Verify base station RTCM3 stream
  STEP 3: Start RTCM injection (user starts rtk_forwarder separately)
  STEP 4: Wait for RTK Fixed (UBX-NAV-PVT carrSoln=2)
  STEP 5: Pixhawk preflight check (pymavlink GPS_RAW_INT)

Integrated modules:
  - F9pRoverConfigurator (rtk_tools/f9p_rover_config.py)  — Task 1
  - F9pFixMonitor         (rtk_tools/f9p_fix_monitor.py)   — Task 2

Usage:
  python rtk_tools/rtk_direct_inject.py
  python rtk_tools/rtk_direct_inject.py --uart-port /dev/ttyAMA4 --timeout 120
  python rtk_tools/rtk_direct_inject.py --skip-f9p-config
  python rtk_tools/rtk_direct_inject.py --log-level DEBUG

Reference:
  docs/05-implementation/rtk_direct_uart2_injection_plan.md  Section 6
"""

import argparse
import csv
import logging
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Allow importing from project root when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rtk_tools.f9p_rover_config import F9pRoverConfigurator
from rtk_tools.f9p_fix_monitor import F9pFixMonitor

logger = logging.getLogger("rtk_direct_inject")

# ---------------------------------------------------------------------------
# GPS fix type name mapping (shared with tools/preflight_check.py)
# ---------------------------------------------------------------------------
FIX_NAMES: dict = {
    -1: "UNKNOWN",
    0: "NO_GPS",
    1: "NO_FIX",
    2: "2D_FIX",
    3: "3D_FIX",
    4: "DGPS",
    5: "RTK_FLOAT",
    6: "RTK_FIXED",
    7: "STATIC",
    8: "PPP",
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class Config:
    """Runtime configuration for the 5-STEP RTK Direct Inject workflow."""

    uart_port: str = "/dev/ttyAMA4"
    uart_baud: int = 115200
    base_host: str = "192.168.11.100"
    base_port: int = 2101
    base_mountpoint: str = "UBLOX_EVK_F9P"
    rtk_fixed_timeout: float = 120.0
    skip_f9p_config: bool = False


# ---------------------------------------------------------------------------
# STEP 1: Configure Rover F9P UART2 (RTCM3 input + UBX output)
# ---------------------------------------------------------------------------

def step1_configure_rover_f9p(cfg: Config) -> bool:
    """Configure Rover F9P UART2 for RTCM3 input + UBX-NAV-PVT output.

    Uses F9pRoverConfigurator (Task 1) to:
      - Set UART2INPROT-RTCM3X=1  (RTCM3 input enabled)
      - Set UART2OUTPROT-UBX=1    (UBX output enabled)
      - Verify settings with CFG-VALGET polling
      - Save to Flash (BBR+Flash)

    Returns:
        True if configured successfully (or skipped), False on failure.
    """
    logger.info("=" * 60)
    logger.info("STEP 1: Configure Rover F9P UART2")
    logger.info("=" * 60)

    if cfg.skip_f9p_config:
        logger.info("  Skipped (--skip-f9p-config)")
        return True

    try:
        configurator = F9pRoverConfigurator(
            serial_port=cfg.uart_port,
            baudrate=cfg.uart_baud,
        )
        results = configurator.configure(save_to_flash=True)

        configured = results.get("uart2_rtcm3_configured", False)
        verified = results.get("uart2_verified", {}).get("all_verified", False)

        if configured and verified:
            logger.info("  UART2 RTCM3 input + UBX output: OK (saved to Flash)")
            return True
        elif configured:
            logger.warning(
                "  UART2 configured but CFG-VALGET verification failed — "
                "continuing (non-critical)"
            )
            return True
        else:
            logger.error("  UART2 configuration failed")
            return False

    except Exception as e:
        logger.error(f"  STEP 1 failed: {e}")
        return False


# ---------------------------------------------------------------------------
# STEP 2: Verify base station RTCM3 stream
# ---------------------------------------------------------------------------

def step2_verify_base_station(cfg: Config) -> bool:
    """Verify the base station NTRIP caster is serving RTCM3 data.

    Performs a proper NTRIP handshake:
      1. TCP connect to base_host:base_port
      2. Send NTRIP GET request with mountpoint and required headers
      3. Check response for ICY 200 OK
      4. Read initial data chunk (512 bytes) and verify RTCM3 preamble (0xD3)

    Returns:
        True only if all checks pass, False otherwise.
    """
    logger.info("=" * 60)
    logger.info("STEP 2: Verify Base Station RTCM3 Stream")
    logger.info("=" * 60)

    sock: Optional[socket.socket] = None

    try:
        # --- 1. TCP connect ---
        logger.info(
            f"  Connecting to {cfg.base_host}:{cfg.base_port} "
            f"(mountpoint: /{cfg.base_mountpoint}) ..."
        )
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((cfg.base_host, cfg.base_port))
        logger.info("  TCP connection established.")

        # --- 2. Send proper NTRIP GET request ---
        request = (
            f"GET /{cfg.base_mountpoint} HTTP/1.1\r\n"
            f"Host: {cfg.base_host}:{cfg.base_port}\r\n"
            f"Ntrip-Version: Ntrip/2.0\r\n"
            f"User-Agent: NTRIP rtk_direct_inject/1.0\r\n"
            f"\r\n"
        )
        logger.debug(f"  Sending NTRIP request:\n{request}")
        sock.sendall(request.encode())

        # --- 3. Check response for ICY 200 OK ---
        resp = b""
        while b"\r\n\r\n" not in resp and len(resp) < 4096:
            chunk = sock.recv(1)
            if not chunk:
                break
            resp += chunk

        response_text = resp.decode("utf-8", errors="replace")
        logger.debug(f"  Response headers (raw):\n{response_text}")

        # NTRIP casters respond with "ICY 200 OK" (not "HTTP/1.1 200 OK")
        first_line = response_text.split("\r\n")[0] if response_text else ""
        if "ICY 200 OK" not in first_line and "200 OK" not in first_line:
            logger.error(
                f"  NTRIP caster returned non-200 response: "
                f"'{first_line.strip()}'"
            )
            return False

        logger.info(f"  NTRIP caster response: {first_line.strip()}")

        # --- 4. Read initial data chunk ---
        sock.settimeout(5.0)
        data = b""
        try:
            while len(data) < 512:
                chunk = sock.recv(512 - len(data))
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            logger.warning("  Timed out waiting for RTCM data stream.")

        if len(data) == 0:
            logger.error(
                "  No RTCM data received from NTRIP caster after ICY 200 OK."
            )
            return False

        # --- 5. Verify RTCM3 preamble (0xD3) ---
        if data[0] != 0xD3:
            logger.error(
                f"  Data does not start with RTCM3 preamble 0xD3: "
                f"first byte = 0x{data[0]:02X}"
            )
            return False

        logger.info(
            f"  RTCM3 stream verified: preamble=0xD3, "
            f"received {len(data)} bytes"
        )
        return True

    except socket.timeout:
        logger.error(
            f"  Connection timeout ({cfg.base_host}:{cfg.base_port}, 10s)"
        )
        return False
    except ConnectionRefusedError:
        logger.error(
            f"  Connection refused by {cfg.base_host}:{cfg.base_port}"
        )
        return False
    except socket.gaierror as e:
        logger.error(
            f"  Cannot resolve host {cfg.base_host}: {e}"
        )
        return False
    except Exception as e:
        logger.error(f"  STEP 2 failed: {e}")
        return False

    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# STEP 3: Start RTCM injection (instruct user — no subprocess)
# ---------------------------------------------------------------------------

def step3_start_rtcm_injection(cfg: Config) -> None:
    """Log the RTCM injection plan and instruct the user to start rtk_forwarder.

    The actual RTCM forwarding is handled by rtk_forwarder_service.py running
    as a separate, long-lived process. This step only prints instructions.
    We never spawn rtk_forwarder as a subprocess because it runs forever.
    """
    logger.info("=" * 60)
    logger.info("STEP 3: Start RTCM Injection")
    logger.info("=" * 60)
    logger.info(f"  UART port    : {cfg.uart_port}")
    logger.info(f"  Baudrate     : {cfg.uart_baud}")
    logger.info(f"  RTCM source  : {cfg.base_host}:{cfg.base_port}")
    logger.info("")
    logger.info("  ┌─────────────────────────────────────────────────────┐")
    logger.info("  │  >>> ACTION REQUIRED: Start rtk_forwarder <<<        │")
    logger.info("  │                                                      │")
    logger.info("  │  Run in another terminal (e.g. via SSH or tmux):      │")
    logger.info("  │                                                      │")
    logger.info("  │    python rtk_tools/rtk_forwarder_service.py         │")
    logger.info("  │      --config config/rtk_forwarder.yml               │")
    logger.info("  │                                                      │")
    logger.info("  │  Ensure the forwarder is configured to output        │")
    logger.info("  │  RTCM data to the serial port above.                 │")
    logger.info("  └─────────────────────────────────────────────────────┘")
    logger.info("")
    logger.info("  ⚠  This script will NOT start rtk_forwarder automatically.")
    logger.info("     It runs as a persistent service and must be started")
    logger.info("     before STEP 4 can succeed.")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# STEP 4: Wait for RTK Fixed (UBX-NAV-PVT carrSoln=2)
# ---------------------------------------------------------------------------

INJECTION_LOG_PATH = os.path.join("logs", "rtcm_injection.log")
FIX_TRANSITION_LOG_PATH = os.path.join("logs", "rtcm_fix_transition.log")
PROOF_SUMMARY_PATH = os.path.join("logs", "rtcm_proof_summary.txt")


def _read_float_fixed_times() -> tuple:
    """rtcm_fix_transition.log から FLOAT/FIXED 到達時間を読み取る。

    Returns:
        (time_to_float, time_to_fixed) — 見つからない場合は None
    """
    time_to_float = None
    time_to_fixed = None
    try:
        with open(FIX_TRANSITION_LOG_PATH, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 9:
                    continue
                transition = row[8]
                elapsed_str = row[1] if len(row) > 1 else ""
                if "FLOAT" in transition and "0→1" in transition:
                    try:
                        time_to_float = float(elapsed_str)
                    except (ValueError, TypeError):
                        pass
                if "FIXED" in transition and "1→2" in transition:
                    try:
                        time_to_fixed = float(elapsed_str)
                    except (ValueError, TypeError):
                        pass
    except (FileNotFoundError, IOError):
        pass
    return time_to_float, time_to_fixed


def _read_injection_stats() -> tuple:
    """rtcm_injection.log の最終行から累積フレーム数・バイト数を読み取る。

    Returns:
        (total_frames, total_bytes) — 読み取れなければ (0, 0)
    """
    try:
        with open(INJECTION_LOG_PATH, "r") as f:
            reader = csv.reader(f)
            last_row = None
            for row in reader:
                if row and not row[0].startswith("#"):
                    last_row = row
            if last_row and len(last_row) >= 3:
                try:
                    frames = int(last_row[1])
                    bytes_total = int(last_row[2])
                    return frames, bytes_total
                except (ValueError, IndexError):
                    pass
    except (FileNotFoundError, IOError):
        pass
    return 0, 0


def _display_and_save_proof_summary(
    start_time: datetime,
    ok: bool,
) -> None:
    """injection_proof_summary を表示し、logs/rtcm_proof_summary.txt に保存する。"""
    end_time = datetime.now()
    time_to_float, time_to_fixed = _read_float_fixed_times()
    total_frames, total_bytes = _read_injection_stats()

    lines = []
    lines.append("=" * 60)
    lines.append("  RTCM INJECTION PROOF SUMMARY")
    lines.append("=" * 60)
    lines.append(f"  RTCM注入開始時刻    : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  RTK FIXED 到達時刻  : {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    total_elapsed = (end_time - start_time).total_seconds()
    lines.append(f"  総経過時間          : {total_elapsed:.1f}s")
    lines.append("")
    lines.append(f"  総注入フレーム数    : {total_frames}")
    lines.append(f"  総注入バイト数      : {total_bytes}")
    lines.append("")
    if time_to_float is not None:
        lines.append(f"  FLOAT 到達までの時間 : {time_to_float:.1f}s")
    else:
        lines.append("  FLOAT 到達までの時間 : (未到達)")
    if time_to_fixed is not None:
        lines.append(f"  FIXED 到達までの時間 : {time_to_fixed:.1f}s")
    else:
        lines.append("  FIXED 到達までの時間 : (未到達)")
    lines.append("")
    lines.append("  ログファイル:")
    lines.append(f"    - RTCM注入ログ       : {INJECTION_LOG_PATH}")
    lines.append(f"    - RTK Fix遷移ログ    : {FIX_TRANSITION_LOG_PATH}")
    lines.append(f"    - 証明サマリ (本ファイル) : {PROOF_SUMMARY_PATH}")
    lines.append("")
    status = "OK (RTK FIXED)" if ok else "NG (NOT FIXED)"
    lines.append(f"  STATUS: {status}")
    lines.append("=" * 60)

    # コンソール表示
    for line in lines:
        logger.info(line)

    # ファイル保存
    os.makedirs("logs", exist_ok=True)
    with open(PROOF_SUMMARY_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info(f"  Proof summary saved to: {PROOF_SUMMARY_PATH}")


def step4_wait_for_rtk_fixed(cfg: Config) -> bool:
    """Poll UART2 for UBX-NAV-PVT and wait until carrSoln=2 (RTK Fixed).

    Uses F9pFixMonitor (Task 2) which reads the UBX-NAV-PVT stream from
    F9P UART2 TX2. The monitor internally logs:
      - Elapsed time, carrSoln name, numSV, hAcc on each poll
      - Position (lat, lon, hMSL), accuracy (hAcc, vAcc), time-to-fix on success

    After completion (success or timeout), an injection_proof_summary is
    displayed and saved to logs/rtcm_proof_summary.txt.

    Returns:
        True if RTK Fixed achieved within timeout, False otherwise.
    """
    logger.info("=" * 60)
    logger.info("STEP 4: Wait for RTK Fixed")
    logger.info(f"  Timeout: {cfg.rtk_fixed_timeout:.0f}s")
    logger.info(f"  Monitoring UBX-NAV-PVT via {cfg.uart_port} ...")
    logger.info("=" * 60)

    start_time = datetime.now()
    monitor: Optional[F9pFixMonitor] = None

    try:
        monitor = F9pFixMonitor(
            serial_port=cfg.uart_port,
            baudrate=cfg.uart_baud,
        )
        monitor.open()
        ok = monitor.wait_for_rtk_fixed(timeout=cfg.rtk_fixed_timeout)

        # RTK Fixed 待機完了後、proof summary を表示・保存
        _display_and_save_proof_summary(start_time, ok)
        return ok

    except Exception as e:
        logger.error(f"  STEP 4 failed: {e}")
        _display_and_save_proof_summary(start_time, False)
        return False

    finally:
        if monitor is not None:
            monitor.close()



# ---------------------------------------------------------------------------
# STEP 5: Pixhawk preflight check (pymavlink GPS_RAW_INT)
# ---------------------------------------------------------------------------

def step5_preflight_check(cfg: Config) -> bool:
    """Check Pixhawk GPS status via MAVLink GPS_RAW_INT message.

    Connects to /dev/ttyAMA0 (default Pixhawk TELEM1 UART) and waits for a
    GPS_RAW_INT message. Reports the fix type and returns True if the fix
    is 3D or better (fix_type >= 3).

    Returns:
        True if fix_type >= 3 (3D fix or better), False otherwise.
    """
    logger.info("=" * 60)
    logger.info("STEP 5: Pixhawk Preflight Check")
    logger.info("=" * 60)

    try:
        from pymavlink import mavutil

        logger.info("  Opening MAVLink connection to /dev/ttyAMA0 @ 115200 ...")
        mav = mavutil.mavlink_connection("/dev/ttyAMA0", baud=115200)

        logger.info("  Waiting for GPS_RAW_INT message (timeout=10s) ...")
        gps_msg = mav.recv_match(
            type="GPS_RAW_INT", blocking=True, timeout=10
        )

        if gps_msg is None:
            logger.warning("  GPS_RAW_INT not received within 10s")
            return False

        ft = gps_msg.fix_type
        fn = FIX_NAMES.get(ft, f"UNKNOWN({ft})")
        logger.info(f"  GPS fix_type={ft} ({fn})")

        if ft >= 6:
            logger.info("  Pixhawk GPS: RTK FIXED — optimal for flight")
            return True
        elif ft >= 3:
            logger.info(f"  Pixhawk GPS: {fn} — 3D fix or better, OK for flight")
            return True
        else:
            logger.warning(
                f"  Pixhawk GPS: {fn} — insufficient for flight "
                f"(need ≥ 3D fix)"
            )
            return False

    except ImportError:
        logger.error(
            "  pymavlink not installed. Install with: pip install pymavlink"
        )
        return False
    except FileNotFoundError as e:
        logger.error(
            f"  Cannot open MAVLink port: {e}. "
            f"Ensure Pixhawk TELEM1 is connected to /dev/ttyAMA0."
        )
        return False
    except Exception as e:
        logger.error(f"  STEP 5 failed: {e}")
        return False



# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    """Execute the 5-STEP RTK Direct UART2 Injection workflow.

    Returns:
        0 if all critical steps passed, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="RTK Direct UART2 Injection — 5-STEP automated workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python rtk_tools/rtk_direct_inject.py\n"
            "  python rtk_tools/rtk_direct_inject.py --timeout 120\n"
            "  python rtk_tools/rtk_direct_inject.py --skip-f9p-config --timeout 60\n"
            "  python rtk_tools/rtk_direct_inject.py --log-level DEBUG\n"
        ),
    )
    parser.add_argument(
        "--uart-port",
        default="/dev/ttyAMA4",
        help="RPi UART4 port connected to F9P (default: /dev/ttyAMA4)",
    )
    parser.add_argument(
        "--uart-baud",
        type=int,
        default=115200,
        help="Serial baudrate (default: 115200)",
    )
    parser.add_argument(
        "--base-host",
        default="192.168.11.100",
        help="Base station NTRIP caster host (default: 192.168.11.100)",
    )
    parser.add_argument(
        "--base-port",
        type=int,
        default=2101,
        help="Base station NTRIP caster port (default: 2101)",
    )
    parser.add_argument(
        "--base-mountpoint",
        default="UBLOX_EVK_F9P",
        help="NTRIP caster mountpoint (default: UBLOX_EVK_F9P)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="RTK Fixed wait timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--skip-f9p-config",
        action="store_true",
        help="Skip STEP 1 F9P UART2 configuration (already configured)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    # --- Logging setup ---
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # --- Build runtime configuration ---
    cfg = Config()
    cfg.uart_port = args.uart_port
    cfg.uart_baud = args.uart_baud
    cfg.base_host = args.base_host
    cfg.base_port = args.base_port
    cfg.base_mountpoint = args.base_mountpoint
    cfg.rtk_fixed_timeout = args.timeout
    cfg.skip_f9p_config = args.skip_f9p_config

    # --- Startup banner ---
    logger.info("")
    logger.info("=" * 60)
    logger.info("  RTK Direct UART2 Injection — 5-STEP Workflow")
    logger.info("=" * 60)
    logger.info(f"  UART port    : {cfg.uart_port} @ {cfg.uart_baud} bps")
    logger.info(f"  Base station : {cfg.base_host}:{cfg.base_port}")
    logger.info(f"  RTK timeout  : {cfg.rtk_fixed_timeout:.0f}s")
    logger.info(f"  Skip config  : {cfg.skip_f9p_config}")
    logger.info("=" * 60)
    logger.info("")

    results: dict = {}

    # --- STEP 1: Configure F9P ---
    results["step1"] = step1_configure_rover_f9p(cfg)
    if not results["step1"]:
        logger.error(
            "STEP 1 failed — cannot proceed without F9P configuration. Abort."
        )
        return 1

    # --- STEP 2: Verify base station ---
    results["step2"] = step2_verify_base_station(cfg)
    if not results["step2"]:
        logger.warning(
            "STEP 2: Base station verification failed. "
            "Continuing (base station may be accessible another way)."
        )

    # --- STEP 3: Instruct user ---
    step3_start_rtcm_injection(cfg)

    # --- STEP 4: Wait for RTK Fixed ---
    results["step4"] = step4_wait_for_rtk_fixed(cfg)
    if not results["step4"]:
        logger.error("STEP 4: RTK Fixed not achieved. Abort.")
        return 1

    # --- STEP 5: Pixhawk preflight check ---
    results["step5"] = step5_preflight_check(cfg)
    if not results["step5"]:
        logger.warning(
            "STEP 5: Pixhawk GPS not ready — "
            "you may need to wait longer for EKF convergence."
        )

    # --- Final summary ---
    all_ok = all(results.values())
    logger.info("")
    logger.info("=" * 60)
    if all_ok:
        logger.info("  FINAL: READY FOR FLIGHT")
    else:
        logger.info("  FINAL: NOT READY")
    logger.info(
        f"  STEP1={'OK' if results.get('step1') else 'FAIL'}, "
        f"STEP2={'OK' if results.get('step2') else 'FAIL'}, "
        f"STEP4={'OK' if results.get('step4') else 'FAIL'}, "
        f"STEP5={'OK' if results.get('step5') else 'FAIL'}"
    )
    logger.info("=" * 60)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
