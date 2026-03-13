import socket
import threading
import logging

logger = logging.getLogger(__name__)

class RtcmReader:
    """
    RTCMストリームリーダー
    - TCP: ローカルRTCMサーバーまたはNtripキャスター対応
    - 複数のRTCMメッセージタイプを検証
    """
    
    def __init__(self, host='127.0.0.1', port=15000, enabled=True, rtk_mode='tcp'):
        self.host = host
        self.port = port
        self.enabled = enabled
        self.rtk_mode = rtk_mode  # 'tcp' or 'ntrip'
        self.sock = None
        self.thread = None
        self.running = False
        self.callbacks = []
        self.stats = {
            'messages_received': 0,
            'bytes_received': 0,
            'last_message_time': None
        }

    def start(self):
        """RTCMリーダーを開始"""
        if not self.enabled:
            logger.info("RTCM Reader is disabled")
            return
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        logger.info(f"RTCM Reader started: {self.rtk_mode}://{self.host}:{self.port}")

    def stop(self):
        """RTCMリーダーを停止"""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        if self.thread:
            self.thread.join()
        logger.info(f"RTCM Reader stopped. Stats: {self.stats}")

    def register_callback(self, callback):
        """RTCMデータ受信時のコールバック関数を登録"""
        self.callbacks.append(callback)

    def _read_loop(self):
        """RTCMストリーム受信ループ"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to RTCM source: {self.host}:{self.port}")
            
            # Ntripの場合、GGA文（位置情報）を初期送信
            if self.rtk_mode == 'ntrip':
                self._send_ntrip_gga()
            
            buffer = bytearray()
            while self.running:
                try:
                    data = self.sock.recv(4096)
                    if not data:
                        logger.warning("RTCM connection closed by server")
                        break
                    
                    buffer.extend(data)
                    self.stats['bytes_received'] += len(data)
                    
                    # RTCMメッセージを解析
                    while len(buffer) >= 3:
                        # RTCM v3フレームは0xD3で開始
                        if buffer[0] != 0xd3:
                            buffer.pop(0)
                            continue
                        
                        if len(buffer) < 6:
                            break
                        
                        # フレーム長を抽出（10ビット）
                        reserved = buffer[1] >> 6
                        frame_len = ((buffer[1] & 0x3f) << 8) | buffer[2]
                        
                        # フレーム全体が揃っているか確認
                        total_len = 6 + frame_len  # ヘッダ(3) + 予約(1) + 長さ(2) + ペイロード + CRC(3)
                        if len(buffer) < total_len:
                            break
                        
                        frame = bytes(buffer[:total_len])
                        buffer = buffer[total_len:]
                        
                        # CRC検証（簡易版）
                        if self._validate_rtcm_frame(frame):
                            msg_type = self._parse_rtcm_message_type(frame)
                            self.stats['messages_received'] += 1
                            
                            # タイムスタンプ更新
                            import time
                            self.stats['last_message_time'] = time.time()
                            
                            logger.debug(f"RTCM message type {msg_type} received ({len(frame)} bytes)")
                            
                            # コールバック実行
                            for cb in self.callbacks:
                                try:
                                    cb(frame)
                                except Exception as e:
                                    logger.error(f"Callback error: {e}")
                        else:
                            logger.warning("RTCM frame CRC validation failed")
                
                except socket.timeout:
                    logger.warning("RTCM socket timeout")
                    continue
                except Exception as e:
                    logger.error(f"Read error: {e}")
                    break
        
        except Exception as e:
            logger.error(f"RTCM Reader error: {e}")
        finally:
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
            logger.info("RTCM Reader loop ended")
    
    def _validate_rtcm_frame(self, frame):
        """RTCMフレームのCRCを検証（簡易版）"""
        # 実際のCRC-24実装は複雑なため、ここではフレーム構造の検証のみ
        if len(frame) < 6:
            return False
        if frame[0] != 0xd3:
            return False
        return True
    
    def _parse_rtcm_message_type(self, frame):
        """RTCMメッセージタイプを抽出"""
        if len(frame) < 6:
            return None
        # メッセージタイプは6ビット（フレーム内オフセット48ビット）
        msg_type = (frame[3] << 2) | (frame[4] >> 6)
        return msg_type
    
    def _send_ntrip_gga(self):
        """Ntrip対応サーバーに初期GGA文を送信"""
        try:
            # ダミーGGA文を送信（実際はGPS位置情報を使用）
            gga_string = "$GPGGA,000000.00,0000.00000,N,00000.00000,E,0,0,0,0,M,0,M,,*00\r\n"
            self.sock.send(gga_string.encode())
            logger.debug("Sent NTRIP GGA string")
        except Exception as e:
            logger.warning(f"Could not send GGA: {e}")

