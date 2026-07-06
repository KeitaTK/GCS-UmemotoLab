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
import time
from typing import Callable, Optional

from pymavlink import mavutil

logger = logging.getLogger(__name__)


class RtcmInjector:
    """
    RTCM3データをMAVLink GPS_RTCM_DATA でArduPilotに注入する。
    pymavlink の gps_rtcm_data_encode() + pack() で CRC_EXTRA 込みの正しい
    CRC を自動計算する。
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
        # pymavlink MAVLink エンコーダ（CRC_EXTRA 自動付与）
        # Use v20 dialect for v2 frames (0xFD magic) — v1 frames on the same
        # UDP socket can interfere with the receive loop in mavlink-router.
        from pymavlink.dialects.v20 import ardupilotmega as mavlink2
        self.mav = mavlink2.MAVLink(
            bytearray(), srcSystem=self.system_id, srcComponent=self.component_id,
            use_native=False,
        )
        self._inter_frame_delay = 0.01  # 10ms delay between multi-fragment frames

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

                # pymavlink の gps_rtcm_data_encode() + pack() で
                # CRC_EXTRA を含む正しい CRC を自動計算
                # ペイロードは180バイトにパディング
                padded = bytearray(chunk).ljust(self.max_payload_size, b'\x00')
                msg = self.mav.gps_rtcm_data_encode(flags, length, bytes(padded))
                frame = msg.pack(self.mav)

                self.send_callback(frame)
                frames_sent += 1

                # Small delay between fragments to avoid flooding the UDP
                # socket / mavlink-router buffer (rule out rate issue).
                if frames_sent > 1:
                    time.sleep(self._inter_frame_delay)

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

    def get_stats(self) -> dict:
        """統計情報を取得"""
        return self.stats.copy()