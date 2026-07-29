#!/usr/bin/env python3
"""
tcp2serial.py — TCP → Serial RTCM3 Bridge (Raspi side)

ntrip_relay.py（Mac）が ichimill NTRIP から受信した RTCM3 を
TCP:2102 に中継するのを受け取り、/dev/ttyAMA4 経由で Rover F9P UART2 に注入する。

パイプライン:
  ichimill NTRIP → ntrip_relay.py (Mac) → TCP:2102 (Tailscale)
                  → tcp2serial.py (Raspi) → /dev/ttyAMA4 → F9P Rover UART2

Usage (on Raspberry Pi):
  python3 scripts/tcp2serial.py
  python3 scripts/tcp2serial.py --listen-port 2102 --serial /dev/ttyAMA4 --baud 115200
"""

import argparse
import logging
import select
import socket
import sys
import time
from collections import deque
from typing import Optional

import serial

RTCM3_PREAMBLE = 0xD3
RTCM3_HEADER_LEN = 3
RTCM3_CRC_LEN = 3
RTCM3_LENGTH_MASK = 0x03

logger = logging.getLogger("tcp2serial")


def extract_message_type(frame: bytes) -> Optional[int]:
    """Extract RTCM3 DF002 12-bit message type from a frame."""
    if len(frame) < 6 or frame[0] != RTCM3_PREAMBLE:
        return None
    payload_len = ((frame[1] & RTCM3_LENGTH_MASK) << 8) | frame[2]
    if len(frame) < RTCM3_HEADER_LEN + payload_len + RTCM3_CRC_LEN:
        return None
    payload = frame[3:3 + payload_len]
    if len(payload) < 2:
        return None
    return (payload[0] << 4) | (payload[1] >> 4)


def parse_rtcm_frame_length(buf):
    """Parse RTCM3 10-bit message length; return total frame length or 0."""
    if len(buf) < 6 or buf[0] != RTCM3_PREAMBLE:
        return 0
    msg_len = ((buf[1] & RTCM3_LENGTH_MASK) << 8) | buf[2]
    return RTCM3_HEADER_LEN + msg_len + RTCM3_CRC_LEN


class StatsRing:
    """Rolling 10-second stats for recent throughput display."""

    def __init__(self, window_sec: float = 10.0):
        self._window = window_sec
        self._samples: deque = deque()

    def add(self, byte_count: int) -> None:
        now = time.monotonic()
        self._samples.append((now, byte_count))
        cutoff = now - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    @property
    def recent_rate_bps(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        elapsed = self._samples[-1][0] - self._samples[0][0]
        if elapsed <= 0:
            return 0.0
        total_bytes = sum(b for _, b in self._samples)
        return total_bytes / elapsed

    @property
    def recent_frame_count(self) -> int:
        return len(self._samples)


def run_server(listen_host: str, listen_port: int,
               serial_port: str, serial_baud: int) -> None:
    """TCP server that accepts one client and forwards to serial."""

    stats = StatsRing(window_sec=10.0)
    total_frames = 0
    total_bytes = 0
    last_report = time.monotonic()
    errors = 0

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((listen_host, listen_port))
    server_sock.listen(1)
    server_sock.settimeout(1.0)

    logger.info(f"TCP server listening on {listen_host}:{listen_port}")
    logger.info(f"Serial target: {serial_port} @ {serial_baud} bps")

    ser: Optional[serial.Serial] = None

    try:
        ser = serial.Serial(serial_port, serial_baud, timeout=0)
        logger.info(f"Serial port opened: {serial_port} @ {serial_baud} bps")

        while True:
            try:
                client, addr = server_sock.accept()
            except socket.timeout:
                continue

            logger.info(f"Client connected: {addr}")
            client.settimeout(0.5)
            client_buffer = bytearray()

            try:
                while True:
                    rlist, _, _ = select.select([client], [], [], 0.5)
                    if client not in rlist:
                        continue

                    try:
                        chunk = client.recv(4096)
                    except socket.timeout:
                        continue

                    if not chunk:
                        logger.info(f"Client {addr} disconnected")
                        break

                    client_buffer.extend(chunk)

                    while len(client_buffer) >= 6:
                        if client_buffer[0] != RTCM3_PREAMBLE:
                            client_buffer.pop(0)
                            continue

                        frame_len = parse_rtcm_frame_length(client_buffer)
                        if frame_len == 0 or len(client_buffer) < frame_len:
                            break

                        frame = bytes(client_buffer[:frame_len])
                        client_buffer = client_buffer[frame_len:]

                        try:
                            ser.write(frame)
                            ser.flush()
                        except serial.SerialException as e:
                            logger.error(f"Serial write error: {e}")
                            errors += 1
                            try:
                                ser.close()
                            except Exception:
                                pass
                            ser = serial.Serial(serial_port, serial_baud, timeout=0)
                            logger.info("Serial port reopened after error")

                        total_frames += 1
                        total_bytes += len(frame)
                        stats.add(len(frame))

                        now = time.monotonic()
                        if now - last_report >= 10:
                            msg_type = extract_message_type(frame)
                            type_str = f"type={msg_type}" if msg_type else "?"
                            logger.info(
                                f"Stats: total={total_frames} frames, "
                                f"{total_bytes:,} bytes | "
                                f"recent={stats.recent_rate_bps:.0f} bps | "
                                f"last: {type_str} ({len(frame)}B) | "
                                f"errors={errors}"
                            )
                            last_report = now

            except (ConnectionResetError, BrokenPipeError) as e:
                logger.warning(f"Client connection lost: {e}")
            except Exception as e:
                logger.error(f"Client handler error: {e}")
                errors += 1
            finally:
                try:
                    client.close()
                except Exception:
                    pass

    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        if ser and ser.is_open:
            ser.close()
            logger.info("Serial port closed")
        server_sock.close()
        logger.info(f"Final: {total_frames} frames, {total_bytes:,} bytes, {errors} errors")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="tcp2serial — TCP→Serial RTCM3 Bridge for Rover F9P UART2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 scripts/tcp2serial.py\n"
            "  python3 scripts/tcp2serial.py --listen-port 2102 --serial /dev/ttyAMA4\n"
        ),
    )
    parser.add_argument(
        "--listen-host", default="0.0.0.0",
        help="TCP listen address (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--listen-port", type=int, default=2102,
        help="TCP listen port (default: 2102)"
    )
    parser.add_argument(
        "--serial", default="/dev/ttyAMA4",
        help="Serial port connected to F9P Rover UART2 RX2"
    )
    parser.add_argument(
        "--baud", type=int, default=115200,
        help="Serial baudrate (default: 115200)"
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 60)
    print("  tcp2serial — RTCM3 TCP→Serial Bridge")
    print(f"  Listen: {args.listen_host}:{args.listen_port}")
    print(f"  Serial: {args.serial} @ {args.baud} bps")
    print("  Pipeline: ntrip_relay→TCP:2102→UART2→F9P Rover")
    print("=" * 60)
    print()

    run_server(args.listen_host, args.listen_port, args.serial, args.baud)


if __name__ == "__main__":
    main()
