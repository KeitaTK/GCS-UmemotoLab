#!/usr/bin/env python3
"""
RTK/RTCM3 Integration Test
- RtcmReader: TCP からのRTCMストリーム受信
- RtcmInjector: GPS_RTCM_DATA (msgid=67) フレーム生成・送信
- エンドツーエンド検証
"""

import sys
import time
import socket
import threading
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'app'))

from mavlink.rtcm_reader import RtcmReader
from mavlink.rtcm_injector import RtcmInjector


class DummyRtcmServer:
    """シミュレーション用ダミーRTCMサーバー"""
    
    def __init__(self, host='127.0.0.1', port=15000):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.client = None
        self.thread = None
    
    def start(self):
        """ダミーサーバーを開始"""
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        time.sleep(0.5)  # サーバー起動を待つ
        logger.info(f"Dummy RTCM server started on {self.host}:{self.port}")
    
    def stop(self):
        """ダミーサーバーを停止"""
        self.running = False
        if self.client:
            try:
                self.client.close()
            except:
                pass
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        if self.thread:
            self.thread.join()
    
    def _run(self):
        """サーバーループ"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            
            while self.running:
                self.socket.settimeout(1)
                try:
                    self.client, addr = self.socket.accept()
                    logger.info(f"Client connected: {addr}")
                    
                    # RTCMデータを送信
                    rtcm_frames = self._generate_rtcm_frames()
                    for frame in rtcm_frames:
                        if not self.running:
                            break
                        self.client.send(frame)
                        time.sleep(0.1)
                    
                    self.client.close()
                    logger.info("Client disconnected")
                    
                except socket.timeout:
                    continue
        
        except Exception as e:
            logger.error(f"Server error: {e}")
    
    def _generate_rtcm_frames(self):
        """テスト用RTCM v3フレームを生成"""
        # RTCM v3フレーム構造:
        # 0xD3 (1) + reserved+len (2) + payload (variable) + CRC24 (3)
        
        frames = []
        
        # フレーム1: Message Type 1001 (L1-only GPS RTK observables)
        # 簡略化されたダミーデータ
        msg_type = 1001
        payload = bytearray()
        payload.append((msg_type >> 6) & 0xFF)
        payload.append(((msg_type & 0x3F) << 2) | 0x00)
        payload.extend(b'\x00' * 25)  # ダミーデータ
        
        frame = self._build_rtcm_frame(payload)
        frames.append(frame)
        
        # フレーム2: Message Type 1002 (L1/L2 GPS RTK observables)
        msg_type = 1002
        payload = bytearray()
        payload.append((msg_type >> 6) & 0xFF)
        payload.append(((msg_type & 0x3F) << 2) | 0x00)
        payload.extend(b'\x00' * 35)  # ダミーデータ
        
        frame = self._build_rtcm_frame(payload)
        frames.append(frame)
        
        # フレーム3: Message Type 1006 (Stationary RTK reference station ARP)
        msg_type = 1006
        payload = bytearray()
        payload.append((msg_type >> 6) & 0xFF)
        payload.append(((msg_type & 0x3F) << 2) | 0x00)
        payload.extend(b'\x00' * 19)  # ダミーデータ
        
        frame = self._build_rtcm_frame(payload)
        frames.append(frame)
        
        return frames
    
    def _build_rtcm_frame(self, payload):
        """RTCM v3フレームを構築"""
        frame = bytearray()
        frame.append(0xD3)  # Start byte
        
        # Reserved (2bit) + Length (10bit)
        length = len(payload)
        len_byte1 = (length >> 8) & 0x3F
        len_byte2 = length & 0xFF
        frame.append(len_byte1)
        frame.append(len_byte2)
        
        # Payload
        frame.extend(payload)
        
        # CRC-24 (簡略版 - 実運用ではきちんと計算が必要)
        crc = 0x000000
        frame.append((crc >> 16) & 0xFF)
        frame.append((crc >> 8) & 0xFF)
        frame.append(crc & 0xFF)
        
        return bytes(frame)


def test_rtcm_reader():
    """RtcmReader テスト"""
    logger.info("=== Testing RtcmReader ===")
    
    # ダミーサーバーを起動
    server = DummyRtcmServer('127.0.0.1', 15000)
    server.start()
    
    # RTCMリーダーを初期化
    reader = RtcmReader(host='127.0.0.1', port=15000, enabled=True)
    
    received_frames = []
    
    def callback(frame):
        received_frames.append(frame)
        logger.info(f"Received RTCM frame: {len(frame)} bytes, msgtype={reader._parse_rtcm_message_type(frame)}")
    
    reader.register_callback(callback)
    reader.start()
    
    # データ受信を待つ
    time.sleep(3)
    
    reader.stop()
    server.stop()
    
    logger.info(f"Received {len(received_frames)} RTCM frames")
    logger.info(f"RtcmReader stats: {reader.stats}")
    
    assert len(received_frames) >= 3, "Expected at least 3 RTCM frames"
    assert reader.stats['messages_received'] >= 3, "Expected at least 3 messages in stats"
    
    logger.info("✓ RtcmReader test PASSED")
    return True


def test_rtcm_injector():
    """RtcmInjector テスト"""
    logger.info("=== Testing RtcmInjector ===")
    
    injector = RtcmInjector(enabled=True, max_payload_size=180)
    
    # MAVLink フレーム送信バッファ
    sent_frames = []
    
    def mock_send(frame):
        sent_frames.append(frame)
        logger.info(f"Sent MAVLink frame: {len(frame)} bytes")
    
    injector.set_send_callback(mock_send)
    
    # RTCMデータ (複数フレーム分)
    rtcm_data = b'\xd3' + (b'\x00' * 500)  # 500バイト以上のダミーデータ
    
    success = injector.inject(rtcm_data)
    
    assert success, "Failed to inject RTCM data"
    assert len(sent_frames) >= 3, "Expected at least 3 MAVLink frames for 500-byte data"
    
    # フレーム検証
    for i, frame in enumerate(sent_frames):
        assert frame[0] == 0xFD, f"Frame {i}: Invalid MAVLink v2 header"
        assert frame[7] == 67, f"Frame {i}: Invalid message ID (expected 67, got {frame[7]})"
    
    stats = injector.get_stats()
    logger.info(f"RtcmInjector stats: {stats}")
    assert stats['rtcm_messages_sent'] == 1, "Expected 1 RTCM message sent"
    assert stats['mavlink_messages_sent'] >= 3, "Expected at least 3 MAVLink messages"
    assert stats['bytes_sent'] == len(rtcm_data), "Byte count mismatch"
    
    logger.info("✓ RtcmInjector test PASSED")
    return True


def test_rtk_integration():
    """RTK統合テスト"""
    logger.info("=== Testing RTK Integration ===")
    
    # ダミーサーバーを起動
    server = DummyRtcmServer('127.0.0.1', 15001)
    server.start()
    
    # RTCMリーダーを初期化
    reader = RtcmReader(host='127.0.0.1', port=15001, enabled=True)
    
    # RTCMインジェクターを初期化
    injector = RtcmInjector(enabled=True)
    
    sent_frames = []
    
    def mock_send(frame):
        sent_frames.append(frame)
        logger.debug(f"Injected: {len(frame)} bytes")
    
    injector.set_send_callback(mock_send)
    
    # RTCMリーダーのコールバックにインジェクターを接続
    def on_rtcm(frame):
        logger.info(f"RTCMリーダー受信: {len(frame)} bytes")
        injector.inject(frame)
    
    reader.register_callback(on_rtcm)
    reader.start()
    
    # データフロー: Server → RTCMリーダー → RTCMインジェクター → MAVLinkフレーム
    time.sleep(3)
    
    reader.stop()
    server.stop()
    
    logger.info(f"Integration test complete:")
    logger.info(f"  - RTCMリーダー受信: {reader.stats['messages_received']} messages")
    logger.info(f"  - MAVLink送信: {len(sent_frames)} frames")
    
    assert reader.stats['messages_received'] >= 3, "Expected at least 3 RTCM messages"
    assert len(sent_frames) >= 3, "Expected at least 3 MAVLink frames"
    
    logger.info("✓ RTK Integration test PASSED")
    return True


def main():
    """すべてのテストを実行"""
    logger.info("=" * 60)
    logger.info("RTK/RTCM3 Integration Test Suite")
    logger.info("=" * 60)
    
    results = []
    
    try:
        results.append(("RtcmReader", test_rtcm_reader()))
    except Exception as e:
        logger.error(f"RtcmReader test failed: {e}", exc_info=True)
        results.append(("RtcmReader", False))
    
    try:
        results.append(("RtcmInjector", test_rtcm_injector()))
    except Exception as e:
        logger.error(f"RtcmInjector test failed: {e}", exc_info=True)
        results.append(("RtcmInjector", False))
    
    try:
        results.append(("RTK Integration", test_rtk_integration()))
    except Exception as e:
        logger.error(f"RTK Integration test failed: {e}", exc_info=True)
        results.append(("RTK Integration", False))
    
    # Summary
    logger.info("=" * 60)
    logger.info("Test Results:")
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"  {name}: {status}")
    
    all_passed = all(r for _, r in results)
    if all_passed:
        logger.info("\n✓✓✓ All tests PASSED ✓✓✓")
        return 0
    else:
        logger.info("\n✗✗✗ Some tests FAILED ✗✗✗")
        return 1


if __name__ == '__main__':
    sys.exit(main())
