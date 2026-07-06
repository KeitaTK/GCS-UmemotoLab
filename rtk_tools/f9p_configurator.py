#!/usr/bin/env python3
"""
F9P Configurator - u-blox ZED-F9P を基地局モード (TMODE3 Fixed) に設定するモジュール

pyubx2 の UBXMessage.config_set() (CFG-VALSET) を使用し、
毎回実行しても冪等な設定を行う。

起動フロー:
  STEP1: TMODE3 Fixed Mode 設定 (CFG-TMODE-MODE=2, 位置設定)
  STEP2: RTCM3 出力メッセージ有効化 (1005/1074/1084/1094/1124/1230)
  STEP3: 設定確認 (CFG-TMODE-MODE をポーリング)
"""

import logging
import time
from typing import Optional

import serial
from pyubx2 import UBXMessage, UBXReader, UBX_PROTOCOL

# ------------------------------------------------------------------
# Layer bitmask for config_set
# ------------------------------------------------------------------
LAYER_RAM = 1
LAYER_BBR = 2
LAYER_FLASH = 4
LAYER_ALL = LAYER_RAM | LAYER_BBR | LAYER_FLASH

# RTCM3 MSGOUT keys for UART1
_RTCM_MSG_KEYS = [
    'CFG-MSGOUT-RTCM_3X_TYPE1005_UART1',  # Station coordinates
    'CFG-MSGOUT-RTCM_3X_TYPE1074_UART1',  # GPS MSM4
    'CFG-MSGOUT-RTCM_3X_TYPE1084_UART1',  # GLONASS MSM4
    'CFG-MSGOUT-RTCM_3X_TYPE1094_UART1',  # Galileo MSM4
    'CFG-MSGOUT-RTCM_3X_TYPE1124_UART1',  # BeiDou MSM4
    'CFG-MSGOUT-RTCM_3X_TYPE1230_UART1',  # GLONASS bias
]

# CFG key IDs for response parsing
_KEY_TMODE_MODE = 0x20030001
_KEY_TMODE_POS_TYPE = 0x20030002


class F9pConfigurator:
    """u-blox ZED-F9P を基地局モード (TMODE3 Fixed) に設定する"""

    def __init__(self, serial_port: str, baudrate: int = 38400,
                 logger: Optional[logging.Logger] = None):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.logger = logger or logging.getLogger("F9pConfigurator")
        self._ser: Optional[serial.Serial] = None
    # ------------------------------------------------------------------
    # シリアル接続管理
    # ------------------------------------------------------------------

    def _open_serial(self) -> serial.Serial:
        self.logger.info(f"Opening serial port: {self.serial_port} @ {self.baudrate}")
        ser = serial.Serial(self.serial_port, self.baudrate, timeout=1.0)
        time.sleep(0.3)
        ser.reset_input_buffer()
        return ser

    def _close_serial(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            self._ser = None

    def _send_ubx(self, msg: bytes) -> None:
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port not open")
        self._ser.write(msg)
        self._ser.flush()

    def _read_ubx_response(self, cls: int, mid: int,
                           timeout: float = 3.0) -> Optional[bytes]:
        """指定された Class/ID の UBX 応答を UBXReader で読み取る"""
        if not self._ser or not self._ser.is_open:
            return None

        ubr = UBXReader(self._ser, protfilter=UBX_PROTOCOL)
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                raw, parsed = ubr.read()
                if parsed and parsed.msg_cls == cls and parsed.msg_id == mid:
                    self.logger.debug(
                        f"Received UBX: cls=0x{cls:02X} mid=0x{mid:02X}"
                    )
                    return raw
            except Exception:
                time.sleep(0.05)

        return None

    # ------------------------------------------------------------------
    # STEP1: TMODE3 Fixed Mode 設定
    # ------------------------------------------------------------------

    def configure_tmode3_fixed(self, lat: float, lon: float, alt: float,
                               save_to_flash: bool = True) -> bool:
        """F9P を TMODE3 Fixed Mode に設定する (CFG-VALSET)"""
        self._ser = self._open_serial()

        try:
            lat_e7 = int(lat * 1e7)
            lon_e7 = int(lon * 1e7)
            alt_cm = int(alt * 100)

            cfg_data = [
                ('CFG-TMODE-MODE', 2),          # 2 = Fixed Mode
                ('CFG-TMODE-POS_TYPE', 0),      # 0 = LLA
                ('CFG-TMODE-LAT', lat_e7),
                ('CFG-TMODE-LON', lon_e7),
                ('CFG-TMODE-HEIGHT', alt_cm),
            ]

            layers = LAYER_ALL if save_to_flash else LAYER_RAM
            msg = UBXMessage.config_set(layers, 0, cfg_data)
            self._send_ubx(msg.serialize())

            self.logger.info(
                f"STEP1: TMODE3 Fixed Mode configured: "
                f"lat={lat:.7f} lon={lon:.7f} alt={alt:.1f}m "
                f"(saved={'Flash' if save_to_flash else 'RAM'})"
            )

            if save_to_flash:
                time.sleep(0.5)

            return True

        except Exception as e:
            self.logger.error(f"STEP1 failed: {e}")
            return False

        finally:
            self._close_serial()

    # ------------------------------------------------------------------
    # STEP2: RTCM3 出力メッセージ有効化
    # ------------------------------------------------------------------

    def enable_rtcm3_output(self, save_to_flash: bool = True) -> bool:
        """RTCM3 出力メッセージを有効化する (CFG-VALSET)"""
        self._ser = self._open_serial()

        try:
            cfg_data = [(key, 1) for key in _RTCM_MSG_KEYS]
            layers = LAYER_ALL if save_to_flash else LAYER_RAM
            msg = UBXMessage.config_set(layers, 0, cfg_data)
            self._send_ubx(msg.serialize())

            self.logger.info(
                f"STEP2: RTCM3 output enabled "
                f"({len(_RTCM_MSG_KEYS)} messages, "
                f"saved={'Flash' if save_to_flash else 'RAM'})"
            )

            if save_to_flash:
                time.sleep(0.5)

            return True

        except Exception as e:
            self.logger.error(f"STEP2 failed: {e}")
            return False

        finally:
            self._close_serial()

    # ------------------------------------------------------------------
    # STEP3: 設定確認
    # ------------------------------------------------------------------

    def check_tmode3(self) -> dict:
        """TMODE3 設定状態を確認する (CFG-VALGET ポーリング)

        Returns:
            dict: {'mode': int, 'mode_name': str, 'pos_type': int, 'verified': bool}
        """
        self._ser = self._open_serial()

        result = {
            'mode': None,
            'mode_name': 'UNKNOWN',
            'pos_type': None,
            'verified': False,
        }

        try:
            poll_msg = UBXMessage.config_poll(0, 0, [
                'CFG-TMODE-MODE',
                'CFG-TMODE-POS_TYPE',
            ])
            self._send_ubx(poll_msg.serialize())

            raw = self._read_ubx_response(0x06, 0x8B, timeout=3.0)

            if raw and len(raw) >= 10:
                payload = raw[6:-2]
                pos = 4  # skip header (version+layer+position)
                while pos + 4 <= len(payload):
                    key_id = int.from_bytes(payload[pos:pos + 4], 'little')
                    pos += 4

                    if key_id == _KEY_TMODE_MODE:
                        if pos < len(payload):
                            result['mode'] = payload[pos]
                            mn = {0: 'DISABLED', 1: 'SURVEY_IN', 2: 'FIXED'}
                            result['mode_name'] = mn.get(
                                result['mode'], f'UNKNOWN({result["mode"]})')
                            pos += 1
                    elif key_id == _KEY_TMODE_POS_TYPE:
                        if pos < len(payload):
                            result['pos_type'] = payload[pos]
                            pos += 1
                    else:
                        break

                result['verified'] = (result['mode'] == 2)
                self.logger.info(
                    f"STEP3: TMODE3 check — mode={result['mode_name']}, "
                    f"pos_type={result['pos_type']}, "
                    f"verified={'OK' if result['verified'] else 'FAIL'}"
                )
            else:
                self.logger.warning("STEP3: No CFG-VALGET response received")

        except Exception as e:
            self.logger.error(f"STEP3 failed: {e}")

        finally:
            self._close_serial()

        return result

    # ------------------------------------------------------------------
    # 統合: 全ステップ実行
    # ------------------------------------------------------------------

    def configure(self, lat: float, lon: float, alt: float,
                  save_to_flash: bool = True) -> dict:
        """F9P 基地局モード設定の全ステップを実行する

        Returns:
            dict: 各ステップの結果 {step1_tmode3, step2_rtcm3, step3_check, all_ok}
        """
        results = {
            'step1_tmode3': False,
            'step2_rtcm3': False,
            'step3_check': {},
            'all_ok': False,
        }

        self.logger.info("=" * 60)
        self.logger.info("F9P Base Station Configuration Started")
        self.logger.info("=" * 60)

        results['step1_tmode3'] = self.configure_tmode3_fixed(
            lat, lon, alt, save_to_flash
        )

        if results['step1_tmode3']:
            results['step2_rtcm3'] = self.enable_rtcm3_output(save_to_flash)
        else:
            self.logger.error("STEP1 failed, skipping STEP2")

        results['step3_check'] = self.check_tmode3()

        results['all_ok'] = (
            results['step1_tmode3']
            and results['step2_rtcm3']
            and results['step3_check'].get('verified', False)
        )

        status = "ALL OK" if results['all_ok'] else "Some steps failed"
        self.logger.info(f"F9P Configuration Result: {status}")
        self.logger.info("=" * 60)

        return results
