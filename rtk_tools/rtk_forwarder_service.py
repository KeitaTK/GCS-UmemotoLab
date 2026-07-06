import argparse
import base64
import logging
import socket
import time
from dataclasses import dataclass
from pathlib import Path

import serial
import yaml

from rtk_tools.config_loader import load_hardware_config
_hw_config = load_hardware_config()


@dataclass
class SourceConfig:
    source_type: str
    host: str
    port: int
    mountpoint: str
    user_agent: str
    username: str
    password: str
    serial_port: str
    baudrate: int
    timeout_sec: float


@dataclass
class ForwardConfig:
    host: str
    port: int


@dataclass
class RetryConfig:
    reconnect_sec: float


@dataclass
class LogConfig:
    level: str
    stats_interval_sec: int


@dataclass
class ServiceConfig:
    source: SourceConfig
    forward: ForwardConfig
    retry: RetryConfig
    log: LogConfig


class RtcmForwarderService:
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.logger = logging.getLogger("rtk_forwarder")
        self.total_packets = 0
        self.total_bytes = 0
        self.last_stats_time = time.time()

    def run_forever(self) -> None:
        self.logger.info(
            "RTK forwarder start: source=%s, forward=%s:%s",
            self.config.source.source_type,
            self.config.forward.host,
            self.config.forward.port,
        )
        while True:
            try:
                if self.config.source.source_type == "ntrip":
                    self._run_ntrip_once()
                elif self.config.source.source_type == "serial":
                    self._run_serial_once()
                else:
                    raise ValueError(
                        "source.source_type must be 'ntrip' or 'serial'"
                    )
            except KeyboardInterrupt:
                self.logger.info("Stopped by user")
                break
            except Exception as exc:
                self.logger.exception("Source loop error: %s", exc)

            self.logger.info(
                "Reconnecting in %.1f sec", self.config.retry.reconnect_sec
            )
            time.sleep(self.config.retry.reconnect_sec)

    def _run_ntrip_once(self) -> None:
        src = self.config.source
        fwd = self.config.forward
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ntrip_sock, socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM
        ) as udp_sock:
            ntrip_sock.settimeout(src.timeout_sec)
            ntrip_sock.connect((src.host, src.port))
            ntrip_sock.sendall(self._build_ntrip_request())
            self.logger.info(
                "Connected to NTRIP caster: %s:%s / %s",
                src.host,
                src.port,
                src.mountpoint,
            )

            first_chunk = ntrip_sock.recv(4096)
            if not first_chunk:
                raise ConnectionError("NTRIP connection closed on initial response")

            header, payload = self._split_header_payload(first_chunk)
            self._check_ntrip_response(header)

            if payload:
                udp_sock.sendto(payload, (fwd.host, fwd.port))
                self._count(payload)

            while True:
                chunk = ntrip_sock.recv(4096)
                if not chunk:
                    raise ConnectionError("NTRIP stream closed by server")
                udp_sock.sendto(chunk, (fwd.host, fwd.port))
                self._count(chunk)

    def _run_serial_once(self) -> None:
        src = self.config.source
        fwd = self.config.forward
        with serial.Serial(src.serial_port, src.baudrate, timeout=src.timeout_sec) as ser, socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM
        ) as udp_sock:
            self.logger.info(
                "Connected to serial source: %s (%sbps)",
                src.serial_port,
                src.baudrate,
            )
            while True:
                # RTCM v3 preamble 0xD3 を探す
                b0 = ser.read(1)
                if not b0:
                    continue
                if b0 != b"\xd3":
                    continue

                header_tail = ser.read(2)
                if len(header_tail) < 2:
                    continue

                payload_len = ((header_tail[0] & 0x03) << 8) | header_tail[1]
                payload_and_crc = ser.read(payload_len + 3)
                if len(payload_and_crc) < payload_len + 3:
                    continue

                frame = b0 + header_tail + payload_and_crc
                udp_sock.sendto(frame, (fwd.host, fwd.port))
                self._count(frame)

    def _build_ntrip_request(self) -> bytes:
        src = self.config.source
        lines = [
            f"GET /{src.mountpoint} HTTP/1.0",
            f"User-Agent: {src.user_agent}",
        ]
        if src.username and src.password:
            token = base64.b64encode(
                f"{src.username}:{src.password}".encode("utf-8")
            ).decode("ascii")
            lines.append(f"Authorization: Basic {token}")
        request = "\r\n".join(lines) + "\r\n\r\n"
        return request.encode("ascii")

    @staticmethod
    def _split_header_payload(chunk: bytes) -> tuple[bytes, bytes]:
        if b"\r\n\r\n" in chunk:
            return chunk.split(b"\r\n\r\n", 1)
        if b"\n\n" in chunk:
            return chunk.split(b"\n\n", 1)
        return chunk, b""

    def _check_ntrip_response(self, header: bytes) -> None:
        text = header.decode(errors="ignore")
        preview = text[:200].replace("\r", " ").replace("\n", " ")
        self.logger.info("NTRIP response: %s", preview)
        if "200" not in text:
            raise ConnectionError(f"NTRIP rejected: {preview}")

    def _count(self, data: bytes) -> None:
        self.total_packets += 1
        self.total_bytes += len(data)

        now = time.time()
        interval = self.config.log.stats_interval_sec
        if now - self.last_stats_time >= interval:
            self.last_stats_time = now
            self.logger.info(
                "Forward stats: packets=%s, bytes=%s",
                self.total_packets,
                self.total_bytes,
            )


def load_config(path: str) -> ServiceConfig:
    """設定ファイルを読み込む。hardware.yml がベース。

    YAML設定ファイルが存在する場合はそれを読み込み、
    hardware.yml の値で上書きする。
    """
    # hardware.yml からデフォルト値を取得
    _hw = _hw_config

    # ベース設定の構築
    source = SourceConfig(
        source_type="ntrip",
        host=_hw.get('forward', {}).get('host', '127.0.0.1'),
        port=2101,  # NTRIP caster default port
        mountpoint="UBLOX_EVK_F9P",
        user_agent="NTRIP PythonClient",
        username="",
        password="",
        serial_port=_hw.get('f9p', {}).get('serial_port', 'COM8'),
        baudrate=_hw.get('f9p', {}).get('baudrate', 115200),
        timeout_sec=2.0,
    )
    forward = ForwardConfig(
        host=_hw.get('forward', {}).get('host', '127.0.0.1'),
        port=_hw.get('forward', {}).get('port', 50010),
    )
    retry = RetryConfig(
        reconnect_sec=_hw.get('retry', {}).get('reconnect_sec', 3.0),
    )
    log = LogConfig(
        level=str(_hw.get('log', {}).get('level', 'INFO')).upper(),
        stats_interval_sec=int(_hw.get('log', {}).get('stats_interval_sec', 5)),
    )

    # YAMLファイルが存在する場合は読み込んで上書き
    if path and Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        source_raw = raw.get("source", {})
        forward_raw = raw.get("forward", {})
        retry_raw = raw.get("retry", {})
        log_raw = raw.get("log", {})

        if source_raw.get("source_type"):
            source.source_type = source_raw["source_type"]
        if source_raw.get("host"):
            source.host = source_raw["host"]
        if source_raw.get("port"):
            source.port = int(source_raw["port"])
        if source_raw.get("mountpoint"):
            source.mountpoint = source_raw["mountpoint"]
        if source_raw.get("user_agent"):
            source.user_agent = source_raw["user_agent"]
        if source_raw.get("username"):
            source.username = source_raw["username"]
        if source_raw.get("password"):
            source.password = source_raw["password"]
        if source_raw.get("serial_port"):
            source.serial_port = source_raw["serial_port"]
        if source_raw.get("baudrate"):
            source.baudrate = int(source_raw["baudrate"])
        if source_raw.get("timeout_sec"):
            source.timeout_sec = float(source_raw["timeout_sec"])

        if forward_raw.get("host"):
            forward.host = forward_raw["host"]
        if forward_raw.get("port"):
            forward.port = int(forward_raw["port"])

        if retry_raw.get("reconnect_sec"):
            retry.reconnect_sec = float(retry_raw["reconnect_sec"])

        if log_raw.get("level"):
            log.level = str(log_raw["level"]).upper()
        if log_raw.get("stats_interval_sec"):
            log.stats_interval_sec = int(log_raw["stats_interval_sec"])

    return ServiceConfig(source=source, forward=forward, retry=retry, log=log)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RTK/RTCM転送サービス（統合版）"
    )
    parser.add_argument(
        "--config",
        default="config/rtk_forwarder.yml",
        help="設定ファイルパス",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    configure_logging(config.log.level)

    service = RtcmForwarderService(config)
    service.run_forever()


if __name__ == "__main__":
    main()
