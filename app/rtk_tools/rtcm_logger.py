"""
RTCMデータバイナリロガー

受信したRTCM3生データとMAVLink注入フレームを
タイムスタンプ付きで logs/ に保存する。
"""

import logging
import struct
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class RtcmLogger:
    """RTCMデータをバイナリログに保存するロガー"""

    def __init__(self, log_dir: str = "logs", enabled: bool = True):
        self.enabled = enabled
        self._lock = threading.Lock()
        self._type_counts: Counter = Counter()
        self._total_frames = 0
        self._total_bytes = 0
        self._first_time: Optional[float] = None
        self._last_time: Optional[float] = None
        self._injector_type_counts: Counter = Counter()
        self._injector_total_frames = 0
        self._injector_total_bytes = 0

        if not enabled:
            self._raw_file = None
            self._inj_file = None
            return

        # logs/ ディレクトリを確保
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # タイムスタンプでファイル名を生成
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._raw_path = log_path / f"rtcm_raw_{ts}.bin"
        self._inj_path = log_path / f"rtcm_injected_{ts}.bin"

        try:
            self._raw_file = open(self._raw_path, "wb")
            logger.info(f"RTCM raw log opened: {self._raw_path}")
        except OSError as e:
            logger.error(f"Failed to open RTCM raw log: {e}")
            self._raw_file = None

        try:
            self._inj_file = open(self._inj_path, "wb")
            logger.info(f"RTCM injected log opened: {self._inj_path}")
        except OSError as e:
            logger.error(f"Failed to open RTCM injected log: {e}")
            self._inj_file = None

    def log_raw(self, data: bytes) -> None:
        """RTCM生フレームをログに記録

        各エントリのバイナリフォーマット:
          [4byte: Unix timestamp (uint32)]
          [2byte: data_length (uint16, big-endian)]
          [N byte: RTCM3 frame data]
        """
        if not self.enabled or not self._raw_file:
            return

        now = time.time()
        with self._lock:
            # フレームのメッセージタイプを解析
            msg_type = self._parse_rtcm_type(data)
            if msg_type is not None:
                self._type_counts[msg_type] += 1

            self._total_frames += 1
            self._total_bytes += len(data)
            if self._first_time is None:
                self._first_time = now
            self._last_time = now

            # ファイル書き込み: timestamp(4) + length(2) + data(N)
            entry = struct.pack("!IH", int(now), len(data)) + data
            self._raw_file.write(entry)
            self._raw_file.flush()

    def log_injected(self, frame: bytes, rtcm_payload: Optional[bytes] = None) -> None:
        """MAVLink注入フレーム（GPS_RTCM_DATA）をログに記録

        各エントリのバイナリフォーマット:
          [4byte: Unix timestamp (uint32)]
          [2byte: frame_length (uint16, big-endian)]
          [N byte: MAVLink v2 frame]
          [2byte: rtcm_payload_length (0 if none)]
          [M byte: RTCM payload (optional)]
        """
        if not self.enabled or not self._inj_file:
            return

        now = time.time()
        with self._lock:
            self._injector_total_frames += 1
            self._injector_total_bytes += len(frame)

            if rtcm_payload:
                # RTCMペイロードからメッセージタイプ解析
                msg_type = self._parse_rtcm_type(rtcm_payload)
                if msg_type is not None:
                    self._injector_type_counts[msg_type] += 1

            # ファイル書き込み
            plen = len(rtcm_payload) if rtcm_payload else 0
            entry = struct.pack("!IH", int(now), len(frame)) + frame
            entry += struct.pack("!H", plen)
            if rtcm_payload:
                entry += rtcm_payload
            self._inj_file.write(entry)
            self._inj_file.flush()

    @staticmethod
    def _parse_rtcm_type(frame: bytes) -> Optional[int]:
        """RTCM3フレームからメッセージタイプを抽出（12ビット）"""
        if len(frame) < 6:
            return None
        if frame[0] != 0xD3:
            return None
        msg_type = (frame[3] << 2) | (frame[4] >> 6)
        return msg_type

    def get_type_counts(self) -> dict:
        """受信RTCMメッセージタイプのカウントを取得"""
        with self._lock:
            return dict(self._type_counts)

    def get_injector_type_counts(self) -> dict:
        """注入したRTCMメッセージタイプのカウントを取得"""
        with self._lock:
            return dict(self._injector_type_counts)

    def get_stats(self) -> dict:
        """統計情報を取得"""
        with self._lock:
            duration = 0
            if self._first_time is not None and self._last_time is not None:
                duration = self._last_time - self._first_time
            return {
                "total_frames": self._total_frames,
                "total_bytes": self._total_bytes,
                "duration_sec": round(duration, 1),
                "type_counts": dict(self._type_counts),
                "injector_frames": self._injector_total_frames,
                "injector_bytes": self._injector_total_bytes,
                "injector_type_counts": dict(self._injector_type_counts),
            }

    def print_stats(self) -> None:
        """統計情報を print() で表示"""
        stats = self.get_stats()
        print("\n" + "=" * 60)
        print("  RTCM Logger Statistics")
        print("=" * 60)

        raw_path = getattr(self, "_raw_path", None)
        inj_path = getattr(self, "_inj_path", None)
        if raw_path:
            print(f"  Raw log:      {raw_path}")
        if inj_path:
            print(f"  Injected log: {inj_path}")

        print(f"  Duration:     {stats['duration_sec']} sec")
        print(f"  Raw frames:   {stats['total_frames']} ({stats['total_bytes']} bytes)")
        if stats['type_counts']:
            print(f"  Raw RTCM types:")
            for t, c in sorted(stats['type_counts'].items()):
                print(f"    Type {t:4d}: {c} frames")
        print(f"  Injected:     {stats['injector_frames']} frames ({stats['injector_bytes']} bytes)")
        if stats['injector_type_counts']:
            print(f"  Injected RTCM types:")
            for t, c in sorted(stats['injector_type_counts'].items()):
                print(f"    Type {t:4d}: {c} frames")
        print("=" * 60 + "\n")

    def close(self) -> None:
        """ログファイルを閉じる"""
        if self._raw_file:
            try:
                self._raw_file.close()
                logger.info(f"RTCM raw log closed: {self._raw_path}")
            except Exception as e:
                logger.error(f"Error closing raw log: {e}")
            self._raw_file = None

        if self._inj_file:
            try:
                self._inj_file.close()
                logger.info(f"RTCM injected log closed: {self._inj_path}")
            except Exception as e:
                logger.error(f"Error closing injected log: {e}")
            self._inj_file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()