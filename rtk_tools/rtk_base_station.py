#!/usr/bin/env python3
"""
RTK Base Station - PC側 RTCM受信・MAVLink送信スクリプト
ublox (F9P等) からシリアルでRTCM受信し、
MAVLink GPS_RTCM_DATA メッセージとして UDP 経由で送信する。

mavlink-router が GPS_RTCM_DATA を透過的に Pixhawk に転送する。
これにより、ラズパイ側の RtcmReader + RtcmInjector が不要になる。

通信経路:
  F9P → USB Serial → rtk_base_station.py → GPS_RTCM_DATA(UDP)
  → SSHトンネル → mavlink-router(UART) → Pixhawk
"""

import argparse
import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass
from queue import Queue, Empty
from pathlib import Path

import serial

from rtk_tools.config_loader import load_config
_cfg = load_config()


@dataclass
class Config:
    """構成データクラス"""
    # シリアルポート設定（ublox接続）
    serial_port: str = "COM8"
    baudrate: int = 115200
    serial_timeout: float = 1.0

    # MAVLink 送信設定（GPS_RTCM_DATA の送信先）
    rtcm_target_host: str = "127.0.0.1"
    rtcm_target_port: int = 14550

    # UDP ブロードキャスト設定（従来の互換性維持用）
    udp_broadcast_host: str = "255.255.255.255"
    udp_broadcast_port: int = 50010
    enable_udp: bool = False

    # ログ設定
    log_level: str = "INFO"
    log_file: str = "rtk_base_station.log"


# ============================================================================
# MAVLink GPS_RTCM_DATA メッセージ作成
# ============================================================================

RtkGpsRtcmDataMsgId = 233  # GPS_RTCM_DATA


def _crc16_ccitt(data: bytes) -> int:
    """CRC-16 CCITT for MAVLink v2 frame checksum."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc <<= 1
            if crc & 0x10000:
                crc ^= 0x1021
        crc &= 0xFFFF
    return crc


def build_gps_rtcm_data_frame(
    rtcm_frame: bytes,
    system_id: int = 255,
    component_id: int = 240,
    seq: int = 0,
    frag_id: int = 0,
    total_frags: int = 1,
    max_payload: int = 180,
) -> list[bytes]:
    """RTCM v3 フレームバイト列を分割し、GPS_RTCM_DATA MAVLink v2 フレーム群を生成する。

    Args:
        rtcm_frame: RTCM v3 フレーム全体（0xD3 で開始）
        system_id: MAVLink システムID（255 = 未使用）
        component_id: MAVLink コンポーネントID
        seq: シーケンス番号（0-255）
        frag_id: フラグメント開始ID
        total_frags: トータルフラグメント数
        max_payload: 1フレームあたりの最大ペイロードサイズ

    Returns:
        list[bytes]: 1つ以上の MAVLink v2 フレーム
    """
    chunks = []
    for i in range(0, len(rtcm_frame), max_payload):
        chunks.append(rtcm_frame[i:i + max_payload])

    total = len(chunks)
    frames = []
    for idx, chunk in enumerate(chunks):
        flags = 0
        if total > 1:
            flags |= 0x01          # fragmented flag
            flags |= (frag_id + idx & 0x03) << 1  # fragment ID

        payload = bytearray(2 + len(chunk))
        payload[0] = flags
        payload[1] = len(chunk) & 0xFF
        payload[2:] = chunk

        # MAVLink v2 フレーム構築
        frame = bytearray()
        frame.append(0xFD)  # MAVLink v2 ヘッダ
        frame.append(len(payload))
        frame.append(0x00)  # incompat flags
        frame.append(0x00)  # compat flags
        frame.append(seq & 0xFF)
        frame.append(system_id)
        frame.append(component_id)
        frame.append(RtkGpsRtcmDataMsgId & 0xFF)
        frame.append((RtkGpsRtcmDataMsgId >> 8) & 0xFF)
        frame.append((RtkGpsRtcmDataMsgId >> 16) & 0xFF)
        frame.extend(payload)
        crc = _crc16_ccitt(frame[1:])
        frame.append(crc & 0xFF)
        frame.append((crc >> 8) & 0xFF)
        frames.append(bytes(frame))

    return frames


# ============================================================================
# RTCM シリアルリーダー
# ============================================================================

class RtcmSerialReader:
    """ublox からのシリアル RTCM読み込み"""

    def __init__(self, config: Config, queue: Queue):
        self.config = config
        self.queue = queue
        self.logger = logging.getLogger("RtcmSerialReader")
        self.running = False
        self.thread = None
        self.stats = {
            'bytes_read': 0,
            'frames_received': 0,
            'read_errors': 0,
            'last_read_time': None
        }

    def start(self):
        """シリアル読み込みを開始"""
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"Serial reader started on {self.config.serial_port}")

    def stop(self):
        """シリアル読み込みを停止"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.logger.info(f"Serial reader stopped. Stats: {self.stats}")

    def _read_loop(self):
        """シリアルポートからデータを読み込むループ

        macOS USB切断時のカーネルブロックを防ぐため、select()で
        読み取り可能チェックを行ってから read() する。
        """
        import select
        ser = None
        try:
            ser = serial.Serial(
                port=self.config.serial_port,
                baudrate=self.config.baudrate,
                timeout=0  # non-blocking — select() で待つ
            )
            self.logger.info(f"Serial port opened: {self.config.serial_port} @ {self.config.baudrate} baud")

            buffer = bytearray()
            fd = ser.fileno()

            while self.running:
                try:
                    # select() で読み取り可能まで待機（最大1秒）
                    ready, _, _ = select.select([fd], [], [], 1.0)
                    if not ready:
                        continue

                    data = ser.read(1024)
                    if not data:
                        continue

                    buffer.extend(data)
                    self.stats['bytes_read'] += len(data)
                    self.stats['last_read_time'] = time.time()

                    # RTCM v3フレーム（0xD3で開始）を抽出
                    while len(buffer) >= 6:
                        if buffer[0] != 0xD3:
                            buffer.pop(0)
                            continue

                        reserved = buffer[1] >> 6
                        frame_len = ((buffer[1] & 0x3F) << 8) | buffer[2]
                        total_len = 6 + frame_len
                        if len(buffer) < total_len:
                            break

                        frame = bytes(buffer[:total_len])
                        buffer = buffer[total_len:]

                        self.queue.put(frame)
                        self.stats['frames_received'] += 1
                        self.logger.debug(f"RTCM frame received: {len(frame)} bytes")

                except (serial.SerialException, OSError, ValueError) as e:
                    self.logger.error(f"Serial read error: {e}")
                    self.stats['read_errors'] += 1
                    time.sleep(1.0)
                    try:
                        ser.close()
                    except:
                        pass
                    try:
                        ser = serial.Serial(
                            port=self.config.serial_port,
                            baudrate=self.config.baudrate,
                            timeout=0
                        )
                        fd = ser.fileno()
                        self.logger.info(f"Serial port reopened: {self.config.serial_port}")
                        buffer = bytearray()
                    except (serial.SerialException, OSError) as e2:
                        self.logger.error(f"Failed to reopen serial: {e2}")
                        break

        except serial.SerialException as e:
            self.logger.error(f"Failed to open serial port: {e}")

        finally:
            if ser and ser.is_open:
                ser.close()


# ============================================================================
# MAVLink GPS_RTCM_DATA 送信機（TcpServer の後継）
# ============================================================================

class MavlinkSender:
    """RTCM フレームを MAVLink GPS_RTCM_DATA メッセージとして UDP 送信する。

    旧 TcpServer（TCP:2101 ブロードキャスト）に代わり、
    MAVLink GPS_RTCM_DATA を mavlink-router に送信する。
    mavlink-router が透過的に Pixhawk へ転送する。
    """

    def __init__(self, config: Config, queue: Queue):
        self.config = config
        self.queue = queue
        self.logger = logging.getLogger("MavlinkSender")
        self.running = False
        self.thread = None
        self.sock = None
        self._seq = 0
        self.stats = {
            'frames_sent': 0,
            'bytes_sent': 0,
            'send_errors': 0
        }

    def start(self):
        """MAVLink 送信を開始"""
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.thread = threading.Thread(target=self._send_loop, daemon=True)
        self.thread.start()
        self.logger.info(
            f"MavlinkSender started: "
            f"{self.config.rtcm_target_host}:{self.config.rtcm_target_port}"
        )

    def stop(self):
        """MAVLink 送信を停止"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.logger.info(f"MavlinkSender stopped. Stats: {self.stats}")

    def _next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) & 0xFF
        return s

    def _send_loop(self):
        """キューから RTCM フレームを取得し、MAVLink 化して UDP 送信"""
        target = (self.config.rtcm_target_host, self.config.rtcm_target_port)
        while self.running:
            try:
                rtcm_frame = self.queue.get(timeout=1)
            except Empty:
                continue

            try:
                seq = self._next_seq()
                mav_frames = build_gps_rtcm_data_frame(
                    rtcm_frame, seq=seq, frag_id=0, total_frags=1
                )
                for mf in mav_frames:
                    self.sock.sendto(mf, target)
                    self.stats['frames_sent'] += 1
                    self.stats['bytes_sent'] += len(mf)
                self.logger.debug(
                    f"Sent {len(mav_frames)} MAVLink frame(s) "
                    f"({len(rtcm_frame)} RTCM bytes)"
                )
            except Exception as e:
                self.logger.error(f"MAVLink send error: {e}")
                self.stats['send_errors'] += 1


# ============================================================================
# UdpBroadcaster（旧互換）
# ============================================================================

class UdpBroadcaster:
    """UDP ブロードキャスト配信（従来互換用、オプション）"""

    def __init__(self, config: Config, queue: Queue):
        self.config = config
        self.queue = queue
        self.logger = logging.getLogger("UdpBroadcaster")
        self.running = False
        self.thread = None
        self.stats = {
            'frames_sent': 0,
            'bytes_sent': 0,
            'broadcast_errors': 0
        }

    def start(self):
        if not self.config.enable_udp:
            self.logger.info("UDP broadcast disabled")
            return
        self.running = True
        self.thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.thread.start()
        self.logger.info(
            f"UDP broadcaster started: "
            f"{self.config.udp_broadcast_host}:{self.config.udp_broadcast_port}"
        )

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.logger.info(f"UDP broadcaster stopped. Stats: {self.stats}")

    def _broadcast_loop(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while self.running:
                try:
                    frame = self.queue.get(timeout=1)
                    sock.sendto(
                        frame,
                        (self.config.udp_broadcast_host, self.config.udp_broadcast_port)
                    )
                    self.stats['frames_sent'] += 1
                    self.stats['bytes_sent'] += len(frame)
                except Empty:
                    continue
                except Exception as e:
                    self.logger.error(f"UDP broadcast error: {e}")
                    self.stats['broadcast_errors'] += 1
        finally:
            if sock:
                sock.close()


# ============================================================================
# RTK 基地局統合
# ============================================================================

class RtkBaseStation:
    """RTK 基地局統合サービス（MAVLink GPS_RTCM_DATA 版）"""

    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("RtkBaseStation")
        self._setup_logging()

        # 共有キュー
        self.rtcm_queue = Queue(maxsize=100)

        # コンポーネント
        self.serial_reader = RtcmSerialReader(config, self.rtcm_queue)
        self.mavlink_sender = MavlinkSender(config, self.rtcm_queue)
        self.udp_broadcaster = UdpBroadcaster(config, self.rtcm_queue)

    def _setup_logging(self):
        log_format = '[%(asctime)s] %(levelname)s %(name)s: %(message)s'

        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, self.config.log_level))
        console_handler.setFormatter(logging.Formatter(log_format))

        file_handler = logging.FileHandler(self.config.log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(log_format))

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    def start(self):
        """基地局を開始"""
        self.logger.info("RTK Base Station starting...")
        self.logger.info(f"  Serial: {self.config.serial_port}")
        self.logger.info(
            f"  MAVLink GPS_RTCM_DATA -> "
            f"{self.config.rtcm_target_host}:{self.config.rtcm_target_port}"
        )
        if self.config.enable_udp:
            self.logger.info(
                f"  UDP: {self.config.udp_broadcast_host}:{self.config.udp_broadcast_port}"
            )

        self.serial_reader.start()
        self.mavlink_sender.start()
        self.udp_broadcaster.start()
        self.logger.info("RTK Base Station started successfully")

    def stop(self):
        self.logger.info("RTK Base Station stopping...")
        self.serial_reader.stop()
        self.mavlink_sender.stop()
        self.udp_broadcaster.stop()
        self.logger.info("RTK Base Station stopped")

    def _read_gps_status(self):
        """Read latest NMEA $GNGGA from serial port for GPS status display."""
        try:
            s = serial.Serial(
                self.config.serial_port, self.config.baudrate, timeout=0.3
            )
            buf = s.read(3000)
            s.close()
            for line in buf.split(b'\n'):
                if line.startswith(b'$GNGGA'):
                    p = line.decode().split(',')
                    if len(p) >= 10 and p[2]:
                        lat_r = float(p[2])
                        lat_deg = int(lat_r / 100)
                        lat = lat_deg + (lat_r - lat_deg * 100) / 60
                        lon_r = float(p[4])
                        lon_deg = int(lon_r / 100)
                        lon = lon_deg + (lon_r - lon_deg * 100) / 60
                        alt = float(p[9]) if p[9] else 0
                        fix = int(p[6]) if p[6] else 0
                        sats = int(p[7]) if p[7] else 0
                        hdop = float(p[8]) if p[8] else 0
                        fix_names = {0: 'NoFix', 1: 'GPS', 2: 'DGPS',
                                     4: 'RTK_FIXED', 5: 'RTK_FLOAT'}
                        return {'lat': lat, 'lon': lon, 'alt': alt,
                                'fix': fix, 'sats': sats, 'hdop': hdop,
                                'fix_name': fix_names.get(fix, f'({fix})')}
        except:
            pass
        return None

    def print_stats(self):
        gps = self._read_gps_status()
        print("\n" + "=" * 70)
        print("RTK Base Station Statistics")
        if gps:
            print(f"  GPS: fix={gps['fix']}({gps['fix_name']}) sats={gps['sats']} "
                  f"lat={gps['lat']:.7f} lon={gps['lon']:.7f} alt={gps['alt']:.1f}m "
                  f"hdop={gps['hdop']:.2f}")
        print("=" * 70)
        print(f"\nSerial Reader:")
        for key, val in self.serial_reader.stats.items():
            print(f"  {key}: {val}")
        print(f"\nMavlinkSender:")
        print(f"  frames_sent: {self.mavlink_sender.stats['frames_sent']}")
        print(f"  bytes_sent: {self.mavlink_sender.stats['bytes_sent']}")
        print(f"  send_errors: {self.mavlink_sender.stats['send_errors']}")
        if self.config.enable_udp:
            print(f"\nUDP Broadcaster:")
            for key, val in self.udp_broadcaster.stats.items():
                print(f"  {key}: {val}")
        print("=" * 70 + "\n")


# ============================================================================
# CLI
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RTK Base Station - ublox RTCM → MAVLink GPS_RTCM_DATA 送信"
    )
    parser.add_argument(
        "--serial-port",
        default=_cfg.get('f9p', {}).get('serial_port', "COM8"),
        help=f"ublox シリアルポート"
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=_cfg.get('f9p', {}).get('baudrate', 115200),
        help="ボーレート"
    )
    parser.add_argument(
        "--rtcm-target",
        default="127.0.0.1:14550",
        help="GPS_RTCM_DATA 送信先 (default: 127.0.0.1:14550)"
    )
    parser.add_argument(
        "--enable-udp",
        action="store_true",
        help="従来のUDPブロードキャストも有効化（互換性用）"
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=50010,
        help="UDPブロードキャストポート (default: 50010)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="ログレベル"
    )
    parser.add_argument(
        "--log-file",
        default="rtk_base_station.log",
        help="ログファイル"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # rtcm-target をパース
    rtcm_host, rtcm_port_str = args.rtcm_target.split(":")
    rtcm_port = int(rtcm_port_str)

    config = Config(
        serial_port=args.serial_port,
        baudrate=args.baudrate,
        rtcm_target_host=rtcm_host,
        rtcm_target_port=rtcm_port,
        enable_udp=args.enable_udp,
        udp_broadcast_port=args.udp_port,
        log_level=args.log_level,
        log_file=args.log_file,
    )

    station = RtkBaseStation(config)
    station.start()

    try:
        while True:
            time.sleep(60)
            station.print_stats()
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    finally:
        station.stop()


if __name__ == "__main__":
    main()