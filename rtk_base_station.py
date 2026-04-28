#!/usr/bin/env python3
"""
RTK Base Station - PC側 RTCM受信・配信スクリプト
ublox (F9P等) からシリアルでRTCM受信し、
TCP/UDP で Raspberry Piへ配信する基地局サービス
"""

import argparse
import logging
import socket
import threading
import time
from dataclasses import dataclass
from queue import Queue, Empty
from pathlib import Path

import serial


@dataclass
class Config:
    """構成データクラス"""
    # シリアルポート設定（ublox接続）
    serial_port: str = "COM8"
    baudrate: int = 115200
    serial_timeout: float = 1.0
    
    # TCP サーバー設定（Raspberry Pi接続）
    tcp_host: str = "0.0.0.0"  # すべてのインターフェースにバインド
    tcp_port: int = 2101
    
    # UDP ブロードキャスト設定（オプション）
    udp_broadcast_host: str = "255.255.255.255"
    udp_broadcast_port: int = 50010
    enable_udp: bool = False
    
    # ログ設定
    log_level: str = "INFO"
    log_file: str = "rtk_base_station.log"


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
        """シリアルポートからデータを読み込むループ"""
        ser = None
        try:
            ser = serial.Serial(
                port=self.config.serial_port,
                baudrate=self.config.baudrate,
                timeout=self.config.serial_timeout
            )
            self.logger.info(f"Serial port opened: {self.config.serial_port} @ {self.config.baudrate} baud")
            
            buffer = bytearray()
            
            while self.running:
                try:
                    # シリアルから1024バイト読み込み
                    data = ser.read(1024)
                    if not data:
                        continue
                    
                    buffer.extend(data)
                    self.stats['bytes_read'] += len(data)
                    self.stats['last_read_time'] = time.time()
                    
                    # RTCM v3フレーム（0xD3で開始）を抽出
                    while len(buffer) >= 6:
                        # RTCM フレームの開始を探す
                        if buffer[0] != 0xD3:
                            buffer.pop(0)
                            continue
                        
                        # フレーム長を解析
                        reserved = buffer[1] >> 6
                        frame_len = ((buffer[1] & 0x3F) << 8) | buffer[2]
                        
                        # フレーム全体が揃っているか確認
                        total_len = 6 + frame_len  # ヘッダ(3) + 予約(1) + 長さ(2) + ペイロード + CRC(3)
                        if len(buffer) < total_len:
                            break
                        
                        # フレームを抽出
                        frame = bytes(buffer[:total_len])
                        buffer = buffer[total_len:]
                        
                        # キューに追加
                        self.queue.put(frame)
                        self.stats['frames_received'] += 1
                        self.logger.debug(f"RTCM frame received: {len(frame)} bytes")
                
                except serial.SerialException as e:
                    self.logger.error(f"Serial read error: {e}")
                    self.stats['read_errors'] += 1
                    time.sleep(0.5)
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
        """TCP サーバーを開始"""
        self.running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        self.logger.info(f"TCP server started on {self.config.tcp_host}:{self.config.tcp_port}")
    
    def stop(self):
        """TCP サーバーを停止"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.logger.info(f"TCP server stopped. Stats: {self.stats}")
    
    def _run_server(self):
        """TCP サーバーループ"""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.config.tcp_host, self.config.tcp_port))
            sock.listen(5)
            self.logger.info(f"TCP listening on {self.config.tcp_host}:{self.config.tcp_port}")
            
            while self.running:
                sock.settimeout(1)
                try:
                    client_sock, client_addr = sock.accept()
                    self.logger.info(f"Client connected: {client_addr}")
                    self.stats['connections'] += 1
                    
                    # クライアントハンドラースレッドを起動
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
        """クライアント接続を処理"""
        client_id = f"{client_addr[0]}:{client_addr[1]}"
        self.stats['clients'].append(client_id)
        
        try:
            frames_sent = 0
            bytes_sent = 0
            
            # キューからフレームを取得して送信
            while self.running:
                try:
                    # キューから最大1秒でフレーム取得
                    frame = self.queue.get(timeout=1)
                    
                    # クライアントに送信
                    client_sock.sendall(frame)
                    frames_sent += 1
                    bytes_sent += len(frame)
                    self.stats['frames_sent'] += 1
                    self.stats['bytes_sent'] += bytes_sent
                    
                    self.logger.debug(f"Sent to {client_id}: {len(frame)} bytes")
                
                except Empty:
                    # キューが空の場合は少し待機
                    continue
                
                except (socket.error, BrokenPipeError) as e:
                    self.logger.warning(f"Client {client_id} disconnected: {e}")
                    break
        
        finally:
            try:
                client_sock.close()
            except:
                pass
            self.stats['clients'].remove(client_id)
            self.logger.info(f"Client {client_id} closed. Sent {frames_sent} frames ({bytes_sent} bytes)")


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
        """UDP ブロードキャスターを開始"""
        if not self.config.enable_udp:
            self.logger.info("UDP broadcast disabled")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"UDP broadcaster started: {self.config.udp_broadcast_host}:{self.config.udp_broadcast_port}")
    
    def stop(self):
        """UDP ブロードキャスターを停止"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.logger.info(f"UDP broadcaster stopped. Stats: {self.stats}")
    
    def _broadcast_loop(self):
        """UDP ブロードキャストループ"""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            while self.running:
                try:
                    frame = self.queue.get(timeout=1)
                    
                    # ブロードキャスト送信
                    sock.sendto(frame, (self.config.udp_broadcast_host, self.config.udp_broadcast_port))
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
    """RTK 基地局統合サービス"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("RtkBaseStation")
        self._setup_logging()
        
        # 共有キュー
        self.rtcm_queue = Queue(maxsize=100)
        
        # コンポーネント
        self.serial_reader = RtcmSerialReader(config, self.rtcm_queue)
        self.tcp_server = TcpServer(config, self.rtcm_queue)
        self.udp_broadcaster = UdpBroadcaster(config, self.rtcm_queue)
    
    def _setup_logging(self):
        """ロギング設定"""
        log_format = '[%(asctime)s] %(levelname)s %(name)s: %(message)s'
        
        # コンソールハンドラー
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, self.config.log_level))
        console_handler.setFormatter(logging.Formatter(log_format))
        
        # ファイルハンドラー
        file_handler = logging.FileHandler(self.config.log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(log_format))
        
        # ルートロガー設定
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
    
    def start(self):
        """基地局を開始"""
        self.logger.info("RTK Base Station starting...")
        self.logger.info(f"  Serial: {self.config.serial_port}")
        self.logger.info(f"  TCP: {self.config.tcp_host}:{self.config.tcp_port}")
        if self.config.enable_udp:
            self.logger.info(f"  UDP: {self.config.udp_broadcast_host}:{self.config.udp_broadcast_port}")
        
        self.serial_reader.start()
        self.tcp_server.start()
        self.udp_broadcaster.start()
        
        self.logger.info("RTK Base Station started successfully")
    
    def stop(self):
        """基地局を停止"""
        self.logger.info("RTK Base Station stopping...")
        self.serial_reader.stop()
        self.tcp_server.stop()
        self.udp_broadcaster.stop()
        self.logger.info("RTK Base Station stopped")
    
    def print_stats(self):
        """統計情報を出力"""
        print("\n" + "=" * 70)
        print("RTK Base Station Statistics")
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


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(
        description="RTK Base Station - ublox からRTCM受信し、TCP/UDP で配信"
    )
    parser.add_argument(
        "--serial-port",
        default="COM8",
        help="ublox シリアルポート (default: COM8)"
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="ボーレート (default: 115200)"
    )
    parser.add_argument(
        "--tcp-host",
        default="0.0.0.0",
        help="TCP バインドホスト (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--tcp-port",
        type=int,
        default=2101,
        help="TCP ポート (default: 2101)"
    )
    parser.add_argument(
        "--enable-udp",
        action="store_true",
        help="UDP ブロードキャスト有効化"
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=50010,
        help="UDP ポート (default: 50010)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="ログレベル (default: INFO)"
    )
    parser.add_argument(
        "--log-file",
        default="rtk_base_station.log",
        help="ログファイル (default: rtk_base_station.log)"
    )
    return parser.parse_args()


def main():
    """メイン関数"""
    args = parse_args()
    
    # 設定を構築
    config = Config(
        serial_port=args.serial_port,
        baudrate=args.baudrate,
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
        enable_udp=args.enable_udp,
        udp_broadcast_port=args.udp_port,
        log_level=args.log_level,
        log_file=args.log_file
    )
    
    # 基地局を起動
    station = RtkBaseStation(config)
    station.start()
    
    try:
        # 定期的に統計情報を出力
        while True:
            time.sleep(60)
            station.print_stats()
    
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    
    finally:
        station.stop()


if __name__ == "__main__":
    main()
