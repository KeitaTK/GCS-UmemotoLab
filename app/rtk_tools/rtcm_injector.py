"""
RTCM3データをMAVLink GPS_RTCM_DATA (#233) でArduPilotに注入する。

pymavlink の gps_rtcm_data_send() 標準関数を使用し、
180バイト超のデータは適切にフラグメント（分割）送信する。

MAVLink仕様:
  - メッセージID: 233 (GPS_RTCM_DATA)
  - 1パケット最大データ長: 180バイト
  - 分割時: flags の LSB=1、ビット1-2にフラグメントID
"""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class RtcmInjector:
    """
    RTCM3データをMAVLink GPS_RTCM_DATA でArduPilotに注入する。
    pymavlink 標準の gps_rtcm_data_send() を使用。
    """

    def __init__(self, enabled: bool = True, max_payload_size: int = 180,
                 system_id: int = 1, component_id: int = 1):
        self.enabled = enabled
        self.max_payload_size = max_payload_size
        self.system_id = system_id
        self.component_id = component_id
        self.send_callback: Optional[Callable] = None
        self.stats = {
            'rtcm_messages_sent': 0,
            'mavlink_frames_sent': 0,
            'bytes_sent': 0,
        }

    def set_send_callback(self, callback: Callable):
        """MAVLinkメッセージ送信関数を設定"""
        self.send_callback = callback

    def inject(self, rtcm_data: bytes) -> bool:
        """
        RTCMデータをArduPilotに注入する。
        180バイト超の場合は自動分割（フラグメント送信）。

        Args:
            rtcm_data: RTCM3 フレームのバイナリデータ

        Returns:
            bool: 送信成功時 True
        """
        if not self.enabled or not self.send_callback:
            return False

        if not rtcm_data or len(rtcm_data) == 0:
            logger.warning("Empty RTCM data")
            return False

        try:
            data_len = len(rtcm_data)
            start = 0
            seq_id = 0
            frames_sent = 0

            while start < data_len:
                length = min(data_len - start, self.max_payload_size)
                chunk = rtcm_data[start:start + length]

                # フラグ設定
                #   Bit 0 (LSB): 1=分割継続, 0=最終フラグメント
                #   Bits 1-2: フラグメントID (0-3)
                flags = 0
                if start + length < data_len:
                    flags |= 0x01  # 続きあり
                fragment_id = (start // self.max_payload_size) & 0x03
                flags |= (fragment_id << 1)

                # pymavlink の gps_rtcm_data_send() を使用
                # ペイロードは180バイトにパディング
                padded = bytearray(chunk).ljust(self.max_payload_size, b'\x00')
                frame = self._build_gps_rtcm_data_frame(flags, length, padded)

                self.send_callback(frame)
                frames_sent += 1

                start += length

            self.stats['rtcm_messages_sent'] += 1
            self.stats['mavlink_frames_sent'] += frames_sent
            self.stats['bytes_sent'] += data_len
            logger.debug(
                f"RTCM injected: {data_len} bytes in {frames_sent} frame(s)"
            )
            return True

        except Exception as e:
            logger.error(f"RTCM injection error: {e}")
            return False

    def _build_gps_rtcm_data_frame(self, flags: int, length: int,
                                   data: bytearray) -> bytes:
        """
        pymavlink の gps_rtcm_data_send() 相当のMAVLink v2フレームを構築する。

        GPS_RTCM_DATA ペイロード構造:
          flags  : uint8_t  — フラグメント情報
          len    : uint8_t  — 有効データ長
          data   : uint8_t[180] — RTCMデータ（パディング込み）

        Returns:
            bytes: MAVLink v2 フレーム
        """
        msgid = 233  # GPS_RTCM_DATA

        # ペイロード構築: flags(1) + len(1) + data(180)
        payload = bytearray(1 + 1 + self.max_payload_size)
        payload[0] = flags & 0xFF
        payload[1] = length & 0xFF
        payload[2:] = data[:self.max_payload_size]

        # MAVLink v2 フレーム構築
        frame = bytearray()
        frame.append(0xFD)  # v2 header
        frame.append(len(payload))  # payload length
        frame.append(0x00)  # incompat flags
        frame.append(0x00)  # compat flags
        frame.append(self._next_seq())
        frame.append(self.system_id)
        frame.append(self.component_id)
        frame.append(msgid & 0xFF)
        frame.append((msgid >> 8) & 0xFF)
        frame.append((msgid >> 16) & 0xFF)
        frame.extend(payload)

        # CRC-16 CCITT (MAVLink v2)
        crc = self._crc16_ccitt(frame[1:])
        frame.append(crc & 0xFF)
        frame.append((crc >> 8) & 0xFF)

        return bytes(frame)

    def _next_seq(self) -> int:
        """簡易シーケンス番号（0-255 ループ）"""
        self._tx_seq = getattr(self, '_tx_seq', 0)
        seq = self._tx_seq & 0xFF
        self._tx_seq = (self._tx_seq + 1) & 0xFF
        return seq

    @staticmethod
    def _crc16_ccitt(data: bytes) -> int:
        """CRC-16 CCITT (MAVLink v2 用、多項式0x1021)"""
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