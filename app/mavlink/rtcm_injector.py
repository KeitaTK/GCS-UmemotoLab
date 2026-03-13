import logging
from typing import Callable

logger = logging.getLogger(__name__)

class RtcmInjector:
    """
    RTCM3データをMAVLink GPS_RTCM_DATA (msgid=67) で送信
    - 大容量RTCMデータの分割送信に対応
    - CRC-16 CCITT チェックサム付き
    """
    
    def __init__(self, enabled=True, max_payload_size=180, system_id=1, component_id=1):
        self.enabled = enabled
        self.max_payload_size = max_payload_size
        self.system_id = system_id
        self.component_id = component_id
        self.send_callback = None
        self.stats = {
            'rtcm_messages_sent': 0,
            'mavlink_messages_sent': 0,
            'bytes_sent': 0
        }

    def set_send_callback(self, callback: Callable):
        """MAVLinkメッセージ送信関数を設定"""
        self.send_callback = callback

    def inject(self, rtcm_data: bytes) -> bool:
        """
        RTCMデータをPixhawkに送信
        - 大容量データは複数フレームに分割
        - 各フレームにシーケンス番号を付与
        """
        if not self.enabled or not self.send_callback:
            return False

        if not rtcm_data or len(rtcm_data) == 0:
            logger.warning("Empty RTCM data")
            return False

        try:
            # データを分割
            chunks = []
            for i in range(0, len(rtcm_data), self.max_payload_size):
                chunk = rtcm_data[i:i + self.max_payload_size]
                chunks.append(chunk)

            total_chunks = len(chunks)
            
            for seq_idx, chunk in enumerate(chunks):
                # GPS_RTCM_DATA メッセージ (msgid=67) を構築
                # 構造: flags(1) + len(2) + data(最大180)
                flags = 0
                data_len = len(chunk)
                
                # フラグに分割情報を含める
                if total_chunks > 1:
                    flags |= 0x01  # 分割フラグ
                    # シーケンス番号を上位ビットに含める
                    flags |= (seq_idx & 0x1F) << 3

                # ペイロードを構築
                payload = bytearray(3 + len(chunk))
                payload[0] = flags
                payload[1] = data_len & 0xFF
                payload[2] = (data_len >> 8) & 0xFF
                payload[3:] = chunk

                # MAVLinkメッセージを送信
                frame = self._build_gps_rtcm_data_message(
                    payload,
                    seq_idx,
                    total_chunks
                )
                
                self.send_callback(frame)
                self.stats['mavlink_messages_sent'] += 1
                
                logger.debug(
                    f"RTCM chunk {seq_idx+1}/{total_chunks} sent "
                    f"({len(chunk)} bytes)"
                )

            self.stats['rtcm_messages_sent'] += 1
            self.stats['bytes_sent'] += len(rtcm_data)
            logger.info(
                f"RTCM data injected: {len(rtcm_data)} bytes in {total_chunks} frame(s)"
            )
            return True

        except Exception as e:
            logger.error(f"RTCM injection error: {e}")
            return False

    def _build_gps_rtcm_data_message(self, payload: bytearray, seq: int, total: int) -> bytes:
        """
        GPS_RTCM_DATA (msgid=67) MAVLink v2メッセージを構築
        
        フレーム構造:
        - Header: 0xFD
        - Payload length: variable (1 byte)
        - Sequence: 1 byte (自動インクリメント)
        - System ID: 1 byte
        - Component ID: 1 byte
        - Message ID: 1 byte (67 = GPS_RTCM_DATA)
        - Payload: up to 255 bytes
        - Checksum: 2 bytes (CRC-16 CCITT)
        """
        msgid = 67  # GPS_RTCM_DATA
        
        # シーケンス番号（0-255でカウントアップ）
        seq_num = seq & 0xFF
        
        # ペイロード長
        payload_len = len(payload)
        
        # フレーム本体を組み立て
        frame = bytearray()
        frame.append(0xFD)  # MAVLink v2 header
        frame.append(payload_len)
        frame.append(0x00)  # incompat flags (always 0 for standard)
        frame.append(0x00)  # compat flags
        frame.append(seq_num)
        frame.append(self.system_id)
        frame.append(self.component_id)
        frame.append(msgid & 0xFF)
        frame.append((msgid >> 8) & 0xFF)
        frame.append((msgid >> 16) & 0xFF)
        frame.extend(payload)
        
        # CRC-16 CCITT チェックサム（MAVLink v2）
        crc = self._crc16_ccitt(frame[1:])  # header以降
        frame.append(crc & 0xFF)
        frame.append((crc >> 8) & 0xFF)
        
        return bytes(frame)

    def _crc16_ccitt(self, data: bytes) -> int:
        """
        CRC-16 CCITT計算（MAVLink v2スタイル）
        初期値: 0xFFFF、多項式: 0x1021
        """
        crc = 0xFFFF
        
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                crc <<= 1
                if crc & 0x10000:
                    crc ^= 0x1021
            crc &= 0xFFFF
        
        return crc

    def get_stats(self) -> dict:
        """統計情報を取得"""
        return self.stats.copy()
