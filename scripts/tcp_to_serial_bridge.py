#!/usr/bin/env python3
"""tcp_to_serial_bridge.py - Raw TCP RTCM → F9P UART2 Serial Bridge

Reads raw RTCM3 frames from TCP server (rtk_base_station_v2.py) and writes
them directly to a serial port connected to the F9P rover UART2.
Also logs injection statistics to logs/rtcm_injection.log.

Usage:
  python scripts/tcp_to_serial_bridge.py \
    --tcp-host 100.80.225.4 --tcp-port 2101 \
    --serial-port /dev/ttyAMA4 --serial-baud 115200
"""

import argparse
import csv
import logging
import os
import socket
import sys
import time

import serial

logger = logging.getLogger("tcp_bridge")

INJECTION_LOG_DIR = "logs"
INJECTION_LOG_FILE = os.path.join(INJECTION_LOG_DIR, "rtcm_injection.log")


class TcpToSerialBridge:
    def __init__(self, tcp_host: str, tcp_port: int,
                 serial_port: str, serial_baud: int):
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.serial_port = serial_port
        self.serial_baud = serial_baud
        self.total_frames = 0
        self.total_bytes = 0
        self.errors = 0
        self._last_frames = 0
        self._last_bytes = 0
        self._last_stats_time = time.time()
        self._csv_file = None
        self._csv_writer = None

    def _init_log(self) -> None:
        os.makedirs(INJECTION_LOG_DIR, exist_ok=True)
        self._csv_file = open(INJECTION_LOG_FILE, "a", newline="")
        self._csv_writer = csv.writer(self._csv_file)
        if os.path.getsize(INJECTION_LOG_FILE) == 0:
            self._csv_writer.writerow([
                "timestamp", "frame_count", "cumulative_bytes",
                "frames_per_min", "bytes_per_minute", "errors",
            ])
            self._csv_file.flush()
        logger.info("Injection log: %s", INJECTION_LOG_FILE)

    def _log_stats(self) -> None:
        now = time.time()
        elapsed = now - self._last_stats_time
        if elapsed <= 0:
            return
        self._last_stats_time = now
        delta_frames = self.total_frames - self._last_frames
        delta_bytes = self.total_bytes - self._last_bytes
        self._last_frames = self.total_frames
        self._last_bytes = self.total_bytes
        frames_per_min = (delta_frames / elapsed) * 60.0
        bytes_per_min = (delta_bytes / elapsed) * 60.0
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
        if self._csv_writer:
            self._csv_writer.writerow([
                timestamp, self.total_frames, self.total_bytes,
                f"{frames_per_min:.1f}", f"{bytes_per_min:.1f}", self.errors,
            ])
            self._csv_file.flush()
        logger.info(
            "Bridge stats: frames=%d bytes=%d rate=%.1f fpm",
            self.total_frames, self.total_bytes, frames_per_min,
        )

    def run(self) -> None:
        self._init_log()
        logger.info(
            "TCP->Serial bridge: %s:%d -> %s @ %d bps",
            self.tcp_host, self.tcp_port, self.serial_port, self.serial_baud,
        )
        while True:
            try:
                self._run_once()
            except KeyboardInterrupt:
                logger.info("Stopped by user")
                break
            except Exception as exc:
                logger.exception("Bridge error: %s", exc)
            logger.info("Reconnecting in 3s...")
            time.sleep(3)

    def _run_once(self) -> None:
        ser = serial.Serial(
            port=self.serial_port, baudrate=self.serial_baud, timeout=1.0,
        )
        ser.reset_output_buffer()
        logger.info("Serial port opened: %s", self.serial_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((self.tcp_host, self.tcp_port))
        logger.info("TCP connected: %s:%d", self.tcp_host, self.tcp_port)
        try:
            stats_interval = 5.0
            last_stats = time.time()
            buf = bytearray()
            while True:
                try:
                    sock.settimeout(1.0)
                    data = sock.recv(4096)
                except socket.timeout:
                    data = b""
                if not data:
                    if time.time() - last_stats > stats_interval:
                        self._log_stats()
                        last_stats = time.time()
                    continue
                buf.extend(data)
                while len(buf) >= 6:
                    if buf[0] != 0xD3:
                        buf.pop(0)
                        continue
                    flen = ((buf[1] & 0x3F) << 8) | buf[2]
                    tlen = 6 + flen
                    if len(buf) < tlen:
                        break
                    frame = bytes(buf[:tlen])
                    buf = buf[tlen:]
                    ser.write(frame)
                    ser.flush()
                    self.total_frames += 1
                    self.total_bytes += len(frame)
                if time.time() - last_stats > stats_interval:
                    self._log_stats()
                    last_stats = time.time()
        finally:
            ser.close()
            sock.close()
            logger.info("Connection closed")

    def close(self) -> None:
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Raw TCP -> F9P UART2 Serial RTCM Bridge",
    )
    parser.add_argument("--tcp-host", default="100.80.225.4")
    parser.add_argument("--tcp-port", type=int, default=2101)
    parser.add_argument("--serial-port", default="/dev/ttyAMA4")
    parser.add_argument("--serial-baud", type=int, default=115200)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    bridge = TcpToSerialBridge(
        tcp_host=args.tcp_host, tcp_port=args.tcp_port,
        serial_port=args.serial_port, serial_baud=args.serial_baud,
    )
    try:
        bridge.run()
    finally:
        bridge.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
