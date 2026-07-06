#!/usr/bin/env python3
"""
RTK Base Station v2 - F9P設定統合版 基地局スクリプト

起動フロー:
  1. JSON設定ファイル (config/base_station.json) を読み込み
  2. F9pConfigurator で F9P を基地局モードに設定（毎回実行、CFG-VALSET で冪等）
     - STEP1: TMODE3 Fixed Mode 設定
     - STEP2: RTCM3 出力メッセージ有効化
     - STEP3: 設定確認（check_tmode3）
  3. シリアルポートを開いて RTCM 受信開始
  4. TCP サーバー起動（ポート 2101）
  5. UDP ブロードキャスト（オプション）

Usage:
  python rtk_base_station_v2.py
  python rtk_base_station_v2.py --config config/base_station.json
  python rtk_base_station_v2.py --tcp-port 2110 --log-level DEBUG
"""

import argparse
import logging
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Optional
import sys

# リポジトリルートを sys.path に追加して rtk_tools をインポート可能にする
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import serial

try:
    from rtk_tools.f9p_configurator import F9pConfigurator
except ModuleNotFoundError:
    from f9p_configurator import F9pConfigurator

try:
    from rtk_tools.standalone_obs import auto_detect_port, auto_observe_position
except ModuleNotFoundError:
    from standalone_obs import auto_detect_port, auto_observe_position

from rtk_tools.config_loader import load_hardware_config
_hw_config = load_hardware_config()


@dataclass
class Config:
    """構成データクラス"""
    # シリアルポート設定（ublox接続）
    serial_port: str = "COM8"
    baudrate: int = 115200
    serial_timeout: float = 1.0

    # F9P 基準局設定
    fixed_lat: Optional[float] = None
    fixed_lon: Optional[float] = None
    fixed_alt: Optional[float] = None
    f9p_baudrate: int = 38400
    skip_f9p_config: bool = False
    save_to_flash: bool = True

    # TCP サーバー設定
    tcp_host: str = "0.0.0.0"
    tcp_port: int = 2101

    # UDP ブロードキャスト設定
    udp_broadcast_host: str = "255.255.255.255"
    udp_broadcast_port: int = 50010
    enable_udp: bool = False

    # ログ設定
    log_level: str = "INFO"
    log_file: str = "rtk_base_station.log"


def _merge_config(json_path: Optional[str], args: argparse.Namespace) -> Config:
    """hardware.yml とCLI引数をマージして Config を生成する

    優先順位: CLI引数 > hardware.yml > デフォルト値

    base_station.mode が "auto" の場合:
      - USBポートを自動検出
      - 設定秒数単独測位で基準座標を自動取得
    """
    config = Config()
    _hw = _hw_config

    # base_station 設定を読み込み
    bs_mode = "manual"
    obs_duration = 60
    if 'base_station' in _hw:
        bs = _hw['base_station']
        bs_mode = bs.get('mode', 'manual')
        obs_duration = int(bs.get('auto_obs_duration', 60))
        config.save_to_flash = bs.get('save_to_flash', config.save_to_flash)

        if bs_mode == 'manual':
            config.fixed_lat = bs.get('fixed_lat')
            config.fixed_lon = bs.get('fixed_lon')
            config.fixed_alt = bs.get('fixed_alt')
        # auto モードの場合は後処理で設定

    # f9p 設定
    if 'f9p' in _hw:
        f9p = _hw['f9p']
        if bs_mode == 'manual':
            config.serial_port = f9p.get('serial_port', config.serial_port)
        config.baudrate = f9p.get('baudrate', config.baudrate)
        config.f9p_baudrate = f9p.get('baudrate', config.f9p_baudrate)

    # forward 設定
    if 'forward' in _hw:
        fwd = _hw['forward']
        config.udp_broadcast_host = fwd.get('host', config.udp_broadcast_host)
        config.udp_broadcast_port = fwd.get('port', config.udp_broadcast_port)

    # CLI 引数で上書き（JSONより優先）
    if hasattr(args, 'tcp_port') and args.tcp_port is not None:
        config.tcp_port = args.tcp_port
    if hasattr(args, 'log_level') and args.log_level is not None:
        config.log_level = args.log_level
    if hasattr(args, 'log_file') and args.log_file is not None:
        config.log_file = args.log_file
    if hasattr(args, 'skip_f9p_config') and args.skip_f9p_config:
        config.skip_f9p_config = True

    # ----- auto モード処理 -----
    if bs_mode == 'auto':
        print("\n" + "=" * 60)
        print("  [AUTO MODE] USBポート自動検出 + 単独測位")
        print("=" * 60)

        # 1. USBポート自動検出
        print("\n【ステップ1/2】USBポートを検出中...")
        config.serial_port = auto_detect_port()

        # 2. 単独測位で基準座標を取得
        print(f"\n【ステップ2/2】単独測位で基準座標を取得中 ({obs_duration}秒)...")
        obs_result = auto_observe_position(
            port=config.serial_port,
            baudrate=config.baudrate,
            duration_sec=obs_duration,
        )

        if obs_result and obs_result['samples'] > 0:
            config.fixed_lat = obs_result['lat']
            config.fixed_lon = obs_result['lon']
            config.fixed_alt = obs_result['alt']
            print(f"  → 基準座標を自動設定しました")
            print(f"    lat={config.fixed_lat:.7f} lon={config.fixed_lon:.7f} "
                  f"alt={config.fixed_alt:.2f}m (HAE)")
        else:
            print("  [WARN] 単独測位に失敗しました。manual モードで再試行してください。")
            sys.exit(1)

    return config


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(
        description="RTK Base Station v2 - F9P統合版 基地局サービス"
    )
    parser.add_argument(
        "--config",
        default=None,
        help="JSON設定ファイルのパス (default: config/base_station.json)"
    )
    parser.add_argument(
        "--tcp-port",
        type=int,
        default=None,
        help="TCPポート（JSONより優先、default: 2101）"
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="ログレベル"
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="ログファイルパス"
    )
    parser.add_argument(
        "--skip-f9p-config",
        action="store_true",
        help="F9P設定をスキップ（事前設定済みの場合）"
    )
    return parser.parse_args()

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
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"Serial reader started on {self.config.serial_port}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.logger.info(f"Serial reader stopped. Stats: {self.stats}")

    def _read_loop(self):
        import select
        ser = None
        try:
            ser = serial.Serial(
                port=self.config.serial_port,
                baudrate=self.config.baudrate,
                timeout=0
            )
            self.logger.info(
                f"Serial port opened: {self.config.serial_port} "
                f"@ {self.config.baudrate} baud"
            )

            buffer = bytearray()
            fd = ser.fileno()

            while self.running:
                try:
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
                        self.logger.debug(f"RTCM frame: {len(frame)} bytes")

                except (serial.SerialException, OSError, ValueError) as e:
                    self.logger.error(f"Serial read error: {e}")
                    self.stats['read_errors'] += 1
                    time.sleep(1.0)
                    try:
                        ser.close()
                    except Exception:
                        pass
                    try:
                        ser = serial.Serial(
                            port=self.config.serial_port,
                            baudrate=self.config.baudrate,
                            timeout=0
                        )
                        fd = ser.fileno()
                        self.logger.info(
                            f"Serial port reopened: {self.config.serial_port}"
                        )
                        buffer = bytearray()
                    except (serial.SerialException, OSError) as e2:
                        self.logger.error(f"Failed to reopen serial: {e2}")
                        break

        except serial.SerialException as e:
            self.logger.error(f"Failed to open serial port: {e}")

        finally:
            if ser and ser.is_open:
                ser.close()


class TcpServer:
    """Raspberry Pi 接続用 TCP サーバー"""

    def __init__(self, config: Config, queue: Queue):
        self.config = config
        self.queue = queue
        self.logger = logging.getLogger("TcpServer")
        self.running = False
        self.thread = None
        self.stats = {
            'connections': 0,
            'frames_sent': 0,
            'bytes_sent': 0,
            'clients': []
        }

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        self.logger.info(
            f"TCP server started on {self.config.tcp_host}:{self.config.tcp_port}"
        )

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.logger.info(f"TCP server stopped. Stats: {self.stats}")

    def _run_server(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.config.tcp_host, self.config.tcp_port))
            sock.listen(5)
            self.logger.info(
                f"TCP listening on {self.config.tcp_host}:{self.config.tcp_port}"
            )

            while self.running:
                sock.settimeout(1)
                try:
                    client_sock, client_addr = sock.accept()
                    self.logger.info(f"Client connected: {client_addr}")
                    self.stats['connections'] += 1

                    client_sock.setsockopt(
                        socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1
                    )
                    try:
                        TCP_KEEPIDLE = (
                            0x10 if hasattr(socket, 'TCP_KEEPALIVE')
                            else socket.TCP_KEEPIDLE
                        )
                        client_sock.setsockopt(
                            socket.IPPROTO_TCP, TCP_KEEPIDLE, 30
                        )
                    except Exception:
                        pass

                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_sock, client_addr),
                        daemon=True
                    )
                    client_thread.start()

                except socket.timeout:
                    continue

        except Exception as e:
            self.logger.error(f"TCP server error: {e}")

        finally:
            if sock:
                sock.close()

    def _handle_client(self, client_sock: socket.socket, client_addr):
        client_id = f"{client_addr[0]}:{client_addr[1]}"
        self.stats['clients'].append(client_id)

        try:
            frames_sent = 0
            bytes_sent = 0

            while self.running:
                try:
                    frame = self.queue.get(timeout=1)
                    client_sock.sendall(frame)
                    frames_sent += 1
                    bytes_sent += len(frame)
                    self.stats['frames_sent'] += 1
                    self.stats['bytes_sent'] += bytes_sent
                    self.logger.debug(
                        f"Sent to {client_id}: {len(frame)} bytes"
                    )

                except Empty:
                    continue
                except (socket.error, BrokenPipeError) as e:
                    self.logger.warning(
                        f"Client {client_id} disconnected: {e}"
                    )
                    break

        finally:
            try:
                client_sock.close()
            except Exception:
                pass
            if client_id in self.stats['clients']:
                self.stats['clients'].remove(client_id)
            self.logger.info(
                f"Client {client_id} closed. "
                f"Sent {frames_sent} frames ({bytes_sent} bytes)"
            )


class UdpBroadcaster:
    """UDP ブロードキャスト配信（オプション）"""

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
        self.thread = threading.Thread(
            target=self._broadcast_loop, daemon=True
        )
        self.thread.start()
        self.logger.info(
            f"UDP broadcaster: {self.config.udp_broadcast_host}:"
            f"{self.config.udp_broadcast_port}"
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
                        (self.config.udp_broadcast_host,
                         self.config.udp_broadcast_port)
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


class RtkBaseStation:
    """RTK 基地局統合サービス (v2: F9P設定統合版)"""

    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("RtkBaseStation")
        self._setup_logging()

        self.rtcm_queue = Queue(maxsize=100)

        self.serial_reader = RtcmSerialReader(config, self.rtcm_queue)
        self.tcp_server = TcpServer(config, self.rtcm_queue)
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

    def _run_f9p_configuration(self) -> bool:
        """F9P基地局モード設定を実行する"""
        if self.config.skip_f9p_config:
            self.logger.info("F9P configuration skipped (--skip-f9p-config)")
            return True

        if (self.config.fixed_lat is None or
                self.config.fixed_lon is None or
                self.config.fixed_alt is None):
            self.logger.warning(
                "F9P fixed position not configured in JSON. "
                "Skipping F9P configuration. "
                "Set 'fixed_lat', 'fixed_lon', 'fixed_alt' in config file."
            )
            return True

        try:
            configurator = F9pConfigurator(
                serial_port=self.config.serial_port,
                baudrate=self.config.f9p_baudrate,
                logger=logging.getLogger("F9pConfigurator")
            )

            results = configurator.configure(
                lat=self.config.fixed_lat,
                lon=self.config.fixed_lon,
                alt=self.config.fixed_alt,
                save_to_flash=self.config.save_to_flash,
            )

            if not results['all_ok']:
                self.logger.warning(
                    "F9P configuration completed with warnings. "
                    "Check logs above for details."
                )

            return results['all_ok']

        except Exception as e:
            self.logger.error(f"F9P configuration error: {e}")
            return False

    def start(self):
        """基地局を開始"""
        self.logger.info("=" * 60)
        self.logger.info("RTK Base Station v2 starting...")
        self.logger.info(f"  Serial: {self.config.serial_port}")
        self.logger.info(f"  TCP: {self.config.tcp_host}:{self.config.tcp_port}")
        if self.config.enable_udp:
            self.logger.info(
                f"  UDP: {self.config.udp_broadcast_host}:"
                f"{self.config.udp_broadcast_port}"
            )
        if self.config.fixed_lat is not None:
            self.logger.info(
                f"  Base position: {self.config.fixed_lat:.7f}, "
                f"{self.config.fixed_lon:.7f}, {self.config.fixed_alt:.1f}m"
            )
        self.logger.info("=" * 60)

        self._run_f9p_configuration()

        self.serial_reader.start()
        self.tcp_server.start()
        self.udp_broadcaster.start()

        self.logger.info("RTK Base Station v2 started successfully")

    def stop(self):
        self.logger.info("RTK Base Station stopping...")
        self.serial_reader.stop()
        self.tcp_server.stop()
        self.udp_broadcaster.stop()
        self.logger.info("RTK Base Station stopped")

    def _read_gps_status(self):
        """Read latest NMEA $GNGGA from serial port for GPS status display."""
        try:
            s = serial.Serial(
                self.config.serial_port,
                self.config.baudrate,
                timeout=0.3
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
                        fix_names = {
                            0: 'NoFix', 1: 'GPS', 2: 'DGPS',
                            4: 'RTK_FIXED', 5: 'RTK_FLOAT'
                        }
                        return {
                            'lat': lat, 'lon': lon, 'alt': alt,
                            'fix': fix, 'sats': sats, 'hdop': hdop,
                            'fix_name': fix_names.get(fix, f'({fix})')
                        }
        except Exception:
            pass
        return None

    def print_stats(self):
        gps = self._read_gps_status()
        print("\n" + "=" * 70)
        print("RTK Base Station v2 Statistics")
        if gps:
            print(
                f"  GPS: fix={gps['fix']}({gps['fix_name']}) "
                f"sats={gps['sats']} "
                f"lat={gps['lat']:.7f} lon={gps['lon']:.7f} "
                f"alt={gps['alt']:.1f}m hdop={gps['hdop']:.2f}"
            )
        print("=" * 70)
        print(f"\nSerial Reader:")
        for key, val in self.serial_reader.stats.items():
            print(f"  {key}: {val}")
        print(f"\nTCP Server:")
        print(f"  connections: {self.tcp_server.stats['connections']}")
        print(f"  frames_sent: {self.tcp_server.stats['frames_sent']}")
        print(f"  bytes_sent: {self.tcp_server.stats['bytes_sent']}")
        print(f"  active_clients: {len(self.tcp_server.stats['clients'])}")
        if self.tcp_server.stats['clients']:
            print(f"    {', '.join(self.tcp_server.stats['clients'])}")
        if self.config.enable_udp:
            print(f"\nUDP Broadcaster:")
            for key, val in self.udp_broadcaster.stats.items():
                print(f"  {key}: {val}")
        print("=" * 70 + "\n")


def main():
    """メイン関数"""
    args = parse_args()

    config = _merge_config(args.config, args)

    print("RTK Base Station v2 Configuration:")
    print(f"  Config file: {args.config or 'config/base_station.json'}")
    print(f"  Serial port: {config.serial_port} @ {config.baudrate}")
    print(f"  TCP: {config.tcp_host}:{config.tcp_port}")
    print(
        f"  F9P config: "
        f"{'skip' if config.skip_f9p_config else 'enabled'}"
    )
    if config.fixed_lat:
        print(f"  Base pos: {config.fixed_lat:.7f}, "
              f"{config.fixed_lon:.7f}, {config.fixed_alt:.1f}m")
    print(f"  Log level: {config.log_level}")
    print()

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

