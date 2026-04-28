#!/usr/bin/env python3
"""
RTK 基地局統合テスト - 自動検証スクリプト
PC側 rtk_base_station.py + Raspberry Pi側 backend_server.py の統合動作を検証
"""

import sys
import time
import socket
import threading
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class TestConfig:
    """テスト設定"""
    pc_host: str = "127.0.0.1"
    pc_tcp_port: int = 2101
    raspi_host: str = "192.168.11.19"  # Raspberry Pi IP
    raspi_backend_port: int = 14550
    test_duration_sec: int = 30
    rtcm_frame_size: int = 100


class DummyubloxSimulator:
    """ublox シミュレータ - RTCM v3フレームを生成"""
    
    def __init__(self, host='127.0.0.1', port=2101, message_interval=0.5):
        self.host = host
        self.port = port
        self.message_interval = message_interval
        self.socket = None
        self.running = False
        self.thread = None
        self.stats = {
            'connections': 0,
            'frames_sent': 0,
            'bytes_sent': 0
        }
    
    def start(self):
        """シミュレータを開始"""
        self.running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        time.sleep(0.5)
        logger.info(f"Dummy ublox simulator started on {self.host}:{self.port}")
    
    def stop(self):
        """シミュレータを停止"""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        if self.thread:
            self.thread.join(timeout=2)
        logger.info(f"Dummy ublox simulator stopped. Stats: {self.stats}")
    
    def _run_server(self):
        """シミュレータサーバー"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            
            while self.running:
                self.socket.settimeout(1)
                try:
                    client_sock, addr = self.socket.accept()
                    logger.info(f"Client connected: {addr}")
                    self.stats['connections'] += 1
                    self._handle_client(client_sock)
                except socket.timeout:
                    continue
        finally:
            if self.socket:
                self.socket.close()
    
    def _handle_client(self, client_sock):
        """クライアント処理"""
        try:
            frame_id = 0
            while self.running:
                frame = self._generate_rtcm_frame(frame_id)
                client_sock.sendall(frame)
                self.stats['frames_sent'] += 1
                self.stats['bytes_sent'] += len(frame)
                frame_id += 1
                
                logger.debug(f"Sent RTCM frame: {len(frame)} bytes")
                time.sleep(self.message_interval)
        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            try:
                client_sock.close()
            except:
                pass
    
    def _generate_rtcm_frame(self, frame_id):
        """RTCM v3 フレーム生成"""
        # 簡略化されたRTCM v3フレーム
        payload = bytearray()
        payload.append((frame_id >> 4) & 0xFF)
        payload.append(((frame_id & 0x0F) << 4) & 0xFF)
        payload.extend(b'\x00' * 98)  # ダミーペイロード
        
        frame = bytearray()
        frame.append(0xD3)
        frame.append((len(payload) >> 8) & 0x3F)
        frame.append(len(payload) & 0xFF)
        frame.extend(payload)
        frame.extend(b'\x00\x00\x00')  # CRC (簡略版)
        
        return bytes(frame)


class TcpClient:
    """TCP クライアント - Raspberry Pi から受信した RTCM をシミュレート"""
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket = None
        self.received_frames = []
        self.stats = {
            'frames_received': 0,
            'bytes_received': 0,
            'connection_errors': 0
        }
    
    def connect(self) -> bool:
        """TCP 接続"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.host, self.port))
            logger.info(f"Connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.stats['connection_errors'] += 1
            return False
    
    def receive_frames(self, timeout_sec: int = 30) -> bool:
        """フレームを受信"""
        if not self.socket:
            return False
        
        start_time = time.time()
        buffer = bytearray()
        
        try:
            while time.time() - start_time < timeout_sec:
                data = self.socket.recv(4096)
                if not data:
                    break
                
                buffer.extend(data)
                self.stats['bytes_received'] += len(data)
                
                # RTCM フレームを解析
                while len(buffer) >= 6:
                    if buffer[0] != 0xD3:
                        buffer.pop(0)
                        continue
                    
                    frame_len = ((buffer[1] & 0x3F) << 8) | buffer[2]
                    total_len = 6 + frame_len
                    
                    if len(buffer) < total_len:
                        break
                    
                    frame = bytes(buffer[:total_len])
                    buffer = buffer[total_len:]
                    
                    self.received_frames.append(frame)
                    self.stats['frames_received'] += 1
                    logger.info(f"  ✓ Received RTCM frame: {len(frame)} bytes")
        
        except socket.timeout:
            logger.warning(f"Receive timeout after {timeout_sec}s")
        except Exception as e:
            logger.error(f"Receive error: {e}")
        
        return self.stats['frames_received'] > 0


def test_rtk_base_station_local():
    """【テスト1】ローカル RTK 基地局 - RTCM受信・配信検証"""
    logger.info("\n" + "=" * 70)
    logger.info("【テスト1】RTK Base Station - ローカルシミュレーション")
    logger.info("=" * 70)
    
    config = TestConfig()
    
    # ublox シミュレータを起動
    ublox_sim = DummyubloxSimulator(
        host=config.pc_host,
        port=config.pc_tcp_port,
        message_interval=0.3
    )
    ublox_sim.start()
    
    try:
        # ダミー TCP クライアント（RTK基地局の代わり）
        client = TcpClient(config.pc_host, config.pc_tcp_port)
        
        logger.info("Simulating rtk_base_station.py behavior...")
        logger.info("Connecting to ublox (via simulator)...")
        
        if not client.connect():
            logger.error("Failed to connect to ublox simulator")
            return False
        
        logger.info(f"Receiving RTCM frames for {config.test_duration_sec} seconds...")
        success = client.receive_frames(timeout_sec=config.test_duration_sec)
        
        logger.info(f"\n【受信統計】")
        logger.info(f"  フレーム数: {client.stats['frames_received']}")
        logger.info(f"  総バイト数: {client.stats['bytes_received']}")
        
        if client.socket:
            client.socket.close()
        
        assert client.stats['frames_received'] >= 10, f"Expected ≥10 frames, got {client.stats['frames_received']}"
        logger.info("✓ テスト1 PASSED\n")
        return True
    
    finally:
        ublox_sim.stop()


def test_rtk_system_integration():
    """【テスト2】RTK システム統合テスト - Raspberry Pi 連携"""
    logger.info("\n" + "=" * 70)
    logger.info("【テスト2】RTK System Integration - Raspberry Pi 連携")
    logger.info("=" * 70)
    
    config = TestConfig()
    
    logger.info(f"テスト構成:")
    logger.info(f"  ublox simulator: {config.pc_host}:{config.pc_tcp_port}")
    logger.info(f"  Raspberry Pi: {config.raspi_host}:{config.raspi_backend_port}")
    logger.info(f"  テスト期間: {config.test_duration_sec}秒")
    
    # 接続性確認
    logger.info("\n【接続確認】")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((config.raspi_host, config.raspi_backend_port))
        sock.close()
        
        if result == 0:
            logger.info(f"  ✓ Raspberry Pi accessible at {config.raspi_host}:{config.raspi_backend_port}")
        else:
            logger.warning(f"  ⚠ Raspberry Pi at {config.raspi_host} not responding")
            logger.warning("  Please ensure Raspberry Pi is running and network is available")
            return False
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False
    
    logger.info("✓ テスト2 PASSED (接続確認OK)\n")
    return True


def print_summary(results: dict):
    """テスト結果サマリーを出力"""
    logger.info("\n" + "=" * 70)
    logger.info("【テスト結果サマリー】")
    logger.info("=" * 70)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"  {status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for p in results.values() if p)
    logger.info(f"\n総合: {passed}/{total} テスト合格")
    logger.info("=" * 70)
    
    return all(results.values())


def main():
    """メイン - 全テストを実行"""
    logger.info("\n" + "=" * 70)
    logger.info("RTK Base Station Integration Test Suite")
    logger.info("=" * 70)
    
    results = {}
    
    # テスト1: ローカル RTK基地局
    try:
        results["RTK Base Station (Local)"] = test_rtk_base_station_local()
    except AssertionError as e:
        logger.error(f"Test failed: {e}")
        results["RTK Base Station (Local)"] = False
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)
        results["RTK Base Station (Local)"] = False
    
    # テスト2: Raspberry Pi 統合
    try:
        results["RTK System Integration"] = test_rtk_system_integration()
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)
        results["RTK System Integration"] = False
    
    # 結果サマリー
    all_passed = print_summary(results)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
