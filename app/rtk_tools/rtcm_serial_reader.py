"""
RTCM Serial Reader — F9P シリアルポートから RTCM3 フレームを直接読み取る。

TCP中継を介さず、同一プロセス内で F9P のシリアルデータを読み取り、
queue.Queue でメインスレッドに受け渡す。
"""

import logging
import threading
import time
from queue import Queue
from typing import Optional

import serial

logger = logging.getLogger(__name__)


class RtcmSerialReader:
    """F9P シリアルポートから RTCM3 フレームを読み取る"""

    def __init__(self, serial_port: str, baudrate: int = 115200,
                 timeout: float = 0.1, queue_maxsize: int = 100,
                 enabled: bool = True):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.timeout = timeout
        self.enabled = enabled
        self.queue: Queue = Queue(maxsize=queue_maxsize)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.stats = {
            'bytes_read': 0,
            'frames_received': 0,
            'read_errors': 0,
            'last_read_time': None,
        }
        self._buffer = bytearray()

    def start(self):
        """シリアル読み取りスレッドを開始"""
        if not self.enabled:
            logger.info("RTCM serial reader is disabled")
            return
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        logger.info(
            f"RTCM serial reader started: {self.serial_port} @ {self.baudrate}"
        )

    def stop(self):
        """シリアル読み取りスレッドを停止"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        logger.info(f"RTCM serial reader stopped. Stats: {self.stats}")

    def _read_loop(self):
        """シリアルポートからRTCMフレームを読み取るメインループ"""
        ser = None
        try:
            ser = serial.Serial(
                port=self.serial_port,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
            logger.info(f"Serial port opened: {self.serial_port} @ {self.baudrate}")

            while self.running:
                try:
                    # データ有無を確認（Windows互換）
                    if ser.in_waiting == 0:
                        time.sleep(0.05)
                        continue

                    data = ser.read(ser.in_waiting)
                    if not data:
                        continue

                    self._buffer.extend(data)
                    self.stats['bytes_read'] += len(data)
                    self.stats['last_read_time'] = time.time()

                    # RTCM v3 フレーム（0xD3 開始）を抽出
                    while len(self._buffer) >= 6:
                        if self._buffer[0] != 0xD3:
                            self._buffer.pop(0)
                            continue

                        # フレーム長を計算（10ビット）
                        reserved = self._buffer[1] >> 6
                        frame_len = ((self._buffer[1] & 0x3F) << 8) | self._buffer[2]
                        total_len = 6 + frame_len  # ヘッダ3 + 予約+長さ2? + ペイロード + CRC3

                        if len(self._buffer) < total_len:
                            break

                        frame = bytes(self._buffer[:total_len])
                        self._buffer = self._buffer[total_len:]

                        # キューに入れる（満杯なら古いものを捨てる）
                        try:
                            self.queue.put_nowait(frame)
                        except Exception:
                            # キュー満杯：古いエントリを捨てる
                            try:
                                self.queue.get_nowait()
                                self.queue.put_nowait(frame)
                            except Exception:
                                pass

                        self.stats['frames_received'] += 1
                        logger.debug(f"RTCM frame: {len(frame)} bytes")

                except (serial.SerialException, OSError) as e:
                    logger.error(f"Serial read error: {e}")
                    self.stats['read_errors'] += 1
                    time.sleep(1.0)
                    # シリアル再接続
                    try:
                        if ser.is_open:
                            ser.close()
                    except Exception:
                        pass
                    try:
                        ser = serial.Serial(
                            port=self.serial_port,
                            baudrate=self.baudrate,
                            timeout=self.timeout,
                        )
                        logger.info(f"Serial port reopened: {self.serial_port}")
                        self._buffer.clear()
                    except (serial.SerialException, OSError) as e2:
                        logger.error(f"Failed to reopen serial: {e2}")
                        break

        except serial.SerialException as e:
            logger.error(f"Failed to open serial port: {e}")

        finally:
            if ser and ser.is_open:
                try:
                    ser.close()
                except Exception:
                    pass