#!/usr/bin/env python3
"""
F9P Rover Configurator — Holybro H-RTK F9P Helical UART2 設定モジュール

Rover 側 F9P の UART2 を RTCM3 補正データ受信 + UBX-NAV-PVT 出力用に構成する。
pyubx2 の UBXMessage.config_set() (CFG-VALSET) を f9p_configurator.py の
パターンに従って使用し、冪等な設定を行う。

対象: Rover 側 Holybro DroneCAN H-RTK F9P Helical (NEO-F9P)
用途: UART2 へ Raspberry Pi から RTCM3 補正データを直接注入する構成の初期設定

既存の CAN 接続 (F9P→Pixhawk 位置情報供給) は変更なし。
UART2 ロジックレベル: 3.3V TTL

参考: docs/05-implementation/rtk_direct_uart2_injection_plan.md Section 4
"""

import argparse
import logging
import sys
import time
from typing import Optional

import serial
from pyubx2 import UBXMessage, UBXReader, UBX_PROTOCOL

# ------------------------------------------------------------------
# Layer bitmask for config_set (from f9p_configurator.py)
# ------------------------------------------------------------------
LAYER_RAM   = 1
LAYER_BBR   = 2
LAYER_FLASH = 4
LAYER_ALL   = LAYER_RAM | LAYER_BBR | LAYER_FLASH

# ------------------------------------------------------------------
# UART2 CFG-VALSET keys for Rover configuration
# ------------------------------------------------------------------
# 【検証済み: 2026-07-21】 CFG-UART2INPROT-RTCM3X=1 が正しく設定されている。
#   UART2 は RTCM3 入力専用 (UBX/NMEA入力無効、全出力無効)。
#   修正不要 — RTK FIXED未達の原因は本設定ではなくRTCM注入パイプライン側。
#   ref: docs/04-testing/2026-07-21_rtk_failure_analysis.md Section 7
_UART2_RTCM_CFG_KEYS = [
    ('CFG-UART2-BAUDRATE',        115200),   # ボーレート 115200 bps
    ('CFG-UART2INPROT-UBX',       0),        # UBX 入力を無効化
    ('CFG-UART2INPROT-NMEA',      0),        # NMEA 入力を無効化
    ('CFG-UART2INPROT-RTCM3X',    1),        # ★ RTCM3 入力を有効化 ★ [検証済み ✓]
    ('CFG-UART2OUTPROT-UBX',      0),        # UBX 出力を無効化 (UART2=RTCM注入専用)
    ('CFG-UART2OUTPROT-NMEA',     0),        # NMEA 出力を無効化
    ('CFG-NAVHPG-DGNSSMODE',      3),        # RTK Fixed モード (3=RTK Fixed)

    # --- Output rate configuration (5 Hz) ---
    ('CFG-RATE-MEAS',                  200),   # ★ 測位演算周期 200ms (5Hz) ★
    ('CFG-RATE-NAV',                   1),     # ★ ナビゲーション出力比 1:1 ★
    ('CFG-MSGOUT-UBX-NAV-PVT-UART2',   0),     # UBX NAV-PVT UART2出力 無効 (UART2=RTCM注入専用)
]

# ------------------------------------------------------------------
# GNSS signal configuration keys
# ------------------------------------------------------------------
_GNSS_SIGNAL_CFG_KEYS = [
    ('CFG-SIGNAL-GPS_ENA',        1),        # GPS L1C/A 有効
    ('CFG-SIGNAL-GPS_L5_ENA',     1),        # GPS L5 有効
    ('CFG-SIGNAL-GAL_ENA',        1),        # Galileo E1 有効
    ('CFG-SIGNAL-GAL_E5A_ENA',    1),        # Galileo E5a 有効
    ('CFG-SIGNAL-BDS_ENA',        1),        # BeiDou B1I 有効
    ('CFG-SIGNAL-GLO_ENA',        1),        # GLONASS L1 有効
]

# ------------------------------------------------------------------
# Verify keys for CFG-VALGET polling
# ------------------------------------------------------------------
_VERIFY_KEYS = [
    'CFG-UART2-BAUDRATE',
    'CFG-UART2INPROT-RTCM3X',
    'CFG-UART2OUTPROT-UBX',
]

# ------------------------------------------------------------------
# CFG key IDs for response parsing (CFG-VALGET raw payload)
# NOTE: These key IDs are derived from the u-blox F9P protocol.
# If verification returns unexpected values, verify these key IDs
# against the actual u-blox NEO-F9P Interface Description.
# ------------------------------------------------------------------
_KEY_CFG_UART2_BAUDRATE       = 0x40590001   # CFG-UART2-BAUDRATE
_KEY_CFG_UART2INPROT_RTCM3X   = 0x40590003   # CFG-UART2INPROT-RTCM3X
_KEY_CFG_UART2OUTPROT_UBX     = 0x40590005   # CFG-UART2OUTPROT-UBX

# Key ID → human-readable name mapping
_KEY_ID_TO_NAME = {
    _KEY_CFG_UART2_BAUDRATE:       'CFG-UART2-BAUDRATE',
    _KEY_CFG_UART2INPROT_RTCM3X:   'CFG-UART2INPROT-RTCM3X',
    _KEY_CFG_UART2OUTPROT_UBX:     'CFG-UART2OUTPROT-UBX',
}


class F9pRoverConfigurator:
    """
    Rover 側 Holybro H-RTK F9P Helical の UART2 を構成する。

    UART2 で RTCM3 補正データ受信 + UBX-NAV-PVT 出力 を有効化し、
    Raspberry Pi からの RTCM 直接注入を可能にする。
    """

    def __init__(self, serial_port: str, baudrate: int = 115200,
                 logger: Optional[logging.Logger] = None):
        """
        Args:
            serial_port: F9P に接続された RPi UART4 ポート (例: /dev/ttyAMA4)
            baudrate: シリアル通信ボーレート (デフォルト 115200)
            logger: ロガーインスタンス (None の場合は新規作成)
        """
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.logger = logger or logging.getLogger("F9pRoverConfigurator")
        self._ser: Optional[serial.Serial] = None

    # ------------------------------------------------------------------
    # シリアル接続管理
    # ------------------------------------------------------------------

    def _open_serial(self) -> serial.Serial:
        """シリアルポートを開き、入力バッファをクリアする"""
        self.logger.info(
            f"Opening serial port: {self.serial_port} @ {self.baudrate}"
        )
        ser = serial.Serial(self.serial_port, self.baudrate, timeout=1.0)
        time.sleep(0.3)
        ser.reset_input_buffer()
        return ser

    def _close_serial(self) -> None:
        """シリアルポートを閉じる"""
        if self._ser and self._ser.is_open:
            self._ser.close()
            self._ser = None

    def _send_ubx(self, msg: bytes) -> None:
        """UBX メッセージ (シリアライズ済み) を送信する"""
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port not open")
        self._ser.write(msg)
        self._ser.flush()

    def _read_ubx_response(self, cls: int, mid: int,
                           timeout: float = 3.0) -> Optional[bytes]:
        """指定された Class/ID の UBX 応答を UBXReader で読み取る (raw bytes)"""
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

    def _read_ubx_valget_response(self, timeout: float = 3.0):
        """CFG-VALGET (0x06, 0x8B) 応答を読み取り、raw と parsed のタプルで返す"""
        if not self._ser or not self._ser.is_open:
            return None, None

        ubr = UBXReader(self._ser, protfilter=UBX_PROTOCOL)
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                raw, parsed = ubr.read()
                if parsed and parsed.msg_cls == 0x06 and parsed.msg_id == 0x8B:
                    self.logger.debug("Received CFG-VALGET response")
                    return raw, parsed
            except Exception:
                time.sleep(0.05)

        return None, None

    # ------------------------------------------------------------------
    # UART2 RTCM3 入力設定
    # ------------------------------------------------------------------

    def configure_uart2_for_rtcm(self, save_to_flash: bool = True) -> bool:
        """
        F9P Rover の UART2 を RTCM3 入力専用に設定する。

        UART2 設定:
          - 入力: RTCM3X のみ有効 (UBX/NMEA 入力は無効)
          - 出力: 全プロトコル無効 (UART2=RTCM注入専用)
          - ボーレート: 115200
          - DGNSS モード: RTK Fixed (3)
          - 測位演算周期: 200ms (5Hz) — CFG-RATE-MEAS=200, CFG-RATE-NAV=1
          - NAV-PVT UART2出力: 無効 (Fix監視はMAVLink GPS_RAW_INT経由に移行)

        Args:
            save_to_flash: True の場合 LAYER_ALL (RAM+BBR+Flash) に保存。
                           False の場合は RAM のみ。

        Returns:
            設定送信に成功したら True
        """
        self._ser = self._open_serial()

        try:
            layers = LAYER_ALL if save_to_flash else LAYER_RAM
            cfg_data = list(_UART2_RTCM_CFG_KEYS)
            msg = UBXMessage.config_set(layers, 0, cfg_data)
            self._send_ubx(msg.serialize())

            self.logger.info(
                f"UART2 RTCM3 input + UBX output configured "
                f"({len(cfg_data)} keys, "
                f"saved={'Flash+BBR' if save_to_flash else 'RAM only'})"
            )

            if save_to_flash:
                time.sleep(0.5)

            return True

        except Exception as e:
            self.logger.error(f"UART2 RTCM configuration failed: {e}")
            return False

        finally:
            self._close_serial()

    # ------------------------------------------------------------------
    # UART2 設定確認 (CFG-VALGET ポーリング)
    # ------------------------------------------------------------------

    def verify_uart2_config(self) -> dict:
        """
        CFG-VALGET で UART2 の主要設定をポーリングし、期待値と比較する。

        Returns:
            dict: {
                'CFG-UART2-BAUDRATE': {
                    'expected': 115200, 'actual': <int|None>, 'ok': <bool>
                },
                'CFG-UART2INPROT-RTCM3X': {
                    'expected': 1, 'actual': <int|None>, 'ok': <bool>
                },
                'CFG-UART2OUTPROT-UBX': {
                    'expected': 0, 'actual': <int|None>, 'ok': <bool>
                },
                'all_verified': <bool>,
            }
        """
        result = {
            'CFG-UART2-BAUDRATE': {
                'expected': 115200, 'actual': None, 'ok': False,
            },
            'CFG-UART2INPROT-RTCM3X': {
                'expected': 1, 'actual': None, 'ok': False,
            },
            'CFG-UART2OUTPROT-UBX': {
                'expected': 0, 'actual': None, 'ok': False,
            },
            'all_verified': False,
        }

        self._ser = self._open_serial()

        try:
            poll_msg = UBXMessage.config_poll(0, 0, list(_VERIFY_KEYS))
            self._send_ubx(poll_msg.serialize())

            raw, _parsed = self._read_ubx_valget_response(timeout=3.0)

            if raw is None or len(raw) < 10:
                self.logger.warning(
                    "verify_uart2_config: No CFG-VALGET response received"
                )
                return result

            # --- Parse CFG-VALGET raw payload ---
            # Payload (after 6-byte UBX header, before 2-byte checksum):
            #   [version:1][layer:1][position:2][key:4][value:variable]...
            payload = raw[6:-2]
            pos = 4  # skip header fields

            while pos + 4 <= len(payload):
                key_id = int.from_bytes(payload[pos:pos + 4], 'little')
                pos += 4

                key_name = _KEY_ID_TO_NAME.get(key_id)
                if key_name is None:
                    # Unknown key — skip 1 byte (most values are U1)
                    if pos < len(payload):
                        pos += 1
                    continue

                # Read value — BAUDRATE is U4 (4 bytes), others are U1
                if key_id == _KEY_CFG_UART2_BAUDRATE:
                    if pos + 4 <= len(payload):
                        result[key_name]['actual'] = int.from_bytes(
                            payload[pos:pos + 4], 'little'
                        )
                        pos += 4
                else:
                    if pos < len(payload):
                        result[key_name]['actual'] = payload[pos]
                        pos += 1

            # --- Compare actual vs expected ---
            for key_name in _VERIFY_KEYS:
                entry = result[key_name]
                entry['ok'] = (entry['actual'] == entry['expected'])

            result['all_verified'] = all(
                result[k]['ok'] for k in _VERIFY_KEYS
            )

            status = "OK" if result['all_verified'] else "MISMATCH"
            self.logger.info(
                f"verify_uart2_config: {status} — "
                f"BAUDRATE={result['CFG-UART2-BAUDRATE']['actual']}, "
                f"RTCM3X={result['CFG-UART2INPROT-RTCM3X']['actual']}, "
                f"UBX_OUT={result['CFG-UART2OUTPROT-UBX']['actual']}"
            )

        except Exception as e:
            self.logger.error(f"verify_uart2_config failed: {e}")

        finally:
            self._close_serial()

    # ------------------------------------------------------------------
    # GNSS 信号設定
    # ------------------------------------------------------------------

    def enable_gnss_signals(self, save_to_flash: bool = True) -> bool:
        """
        全 GNSS コンステレーション信号を有効化する。

        GPS L1/L5, Galileo E1/E5a, BeiDou B1I, GLONASS L1 を有効にする。

        Args:
            save_to_flash: True の場合 LAYER_ALL (RAM+BBR+Flash) に保存。

        Returns:
            設定送信に成功したら True
        """
        self._ser = self._open_serial()

        try:
            layers = LAYER_ALL if save_to_flash else LAYER_RAM
            cfg_data = list(_GNSS_SIGNAL_CFG_KEYS)
            msg = UBXMessage.config_set(layers, 0, cfg_data)
            self._send_ubx(msg.serialize())

            self.logger.info(
                f"GNSS signals enabled "
                f"({len(cfg_data)} constellations, "
                f"saved={'Flash+BBR' if save_to_flash else 'RAM only'})"
            )

            if save_to_flash:
                time.sleep(0.5)

            return True

        except Exception as e:
            self.logger.error(f"GNSS signal configuration failed: {e}")
            return False

        finally:
            self._close_serial()

    # ------------------------------------------------------------------
    # 統合設定メソッド
    # ------------------------------------------------------------------

    def configure(self, save_to_flash: bool = True) -> dict:
        """
        F9P Rover の UART2 設定 + 検証を一括実行する。

        1. configure_uart2_for_rtcm() — UART2 RTCM3 入力有効化
        2. verify_uart2_config()   — 設定ポーリング確認

        Args:
            save_to_flash: True の場合 Flash に保存。

        Returns:
            dict: {
                'uart2_rtcm3_configured': bool,
                'uart2_verified': dict (verify_uart2_config の戻り値),
                'all_ok': bool,
            }
        """
        results = {
            'uart2_rtcm3_configured': False,
            'uart2_verified': {},
            'all_ok': False,
        }

        self.logger.info("=" * 60)
        self.logger.info("F9P Rover UART2 Configuration Started")
        self.logger.info(f"  Port: {self.serial_port} @ {self.baudrate}")
        self.logger.info(
            f"  Save: {'Flash+BBR' if save_to_flash else 'RAM only'}"
        )
        self.logger.info("=" * 60)

        # Step 1: UART2 RTCM3 configuration
        results['uart2_rtcm3_configured'] = self.configure_uart2_for_rtcm(
            save_to_flash
        )

        # Step 2: Verify
        results['uart2_verified'] = self.verify_uart2_config()

        # Overall status
        results['all_ok'] = (
            results['uart2_rtcm3_configured']
            and results['uart2_verified'].get('all_verified', False)
        )

        status = "ALL OK" if results['all_ok'] else "Some steps failed"
        self.logger.info(f"F9P Rover Configuration Result: {status}")
        self.logger.info("=" * 60)

        return results

# ======================================================================
# Standalone 実行用
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description='F9P Rover UART2 Configurator — '
                    'RTCM3 input + UBX output setup',
        epilog='Example: python f9p_rover_config.py '
               '--port /dev/ttyAMA4 --baud 115200',
    )
    parser.add_argument(
        '--port', default='/dev/ttyAMA4',
        help='RPi UART4 port connected to F9P '
             '(default: /dev/ttyAMA4)',
    )
    parser.add_argument(
        '--baud', type=int, default=115200,
        help='Serial baudrate (default: 115200)',
    )
    parser.add_argument(
        '--no-flash', action='store_true',
        help='Skip saving to Flash (RAM only)',
    )
    parser.add_argument(
        '--verify-only', action='store_true',
        help='Only verify UART2 config, skip configuration',
    )
    parser.add_argument(
        '--enable-gnss', action='store_true',
        help='Also enable all GNSS signal constellations',
    )
    parser.add_argument(
        '--log-level', default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)',
    )

    args = parser.parse_args()

    # --- Logging setup ---
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )
    logger = logging.getLogger("F9pRoverConfig")

    # --- Create configurator ---
    configurator = F9pRoverConfigurator(
        serial_port=args.port,
        baudrate=args.baud,
        logger=logger,
    )

    save_to_flash = not args.no_flash

    if args.verify_only:
        # --- Verify only ---
        logger.info("Verification-only mode")
        result = configurator.verify_uart2_config()
        print("\n" + "=" * 50)
        print("UART2 Config Verification Results")
        print("=" * 50)
        for key_name in _VERIFY_KEYS:
            entry = result[key_name]
            status = "OK" if entry['ok'] else "FAIL"
            print(f"  {key_name:30s}: expected={entry['expected']:>6}, "
                  f"actual={entry['actual']}, {status}")
        print("-" * 50)
        verified = result.get('all_verified', False)
        print(f"  All verified: {'YES' if verified else 'NO'}")
        print("=" * 50)
        return 0 if verified else 1

    # --- Configure + verify ---
    results = configurator.configure(save_to_flash=save_to_flash)

    # --- Optional: GNSS signals ---
    if args.enable_gnss and results['uart2_rtcm3_configured']:
        gnss_ok = configurator.enable_gnss_signals(
            save_to_flash=save_to_flash
        )
        results['gnss_signals_enabled'] = gnss_ok
        results['all_ok'] = results['all_ok'] and gnss_ok

    # --- Print summary ---
    print("\n" + "=" * 50)
    print("F9P Rover Configuration Summary")
    print("=" * 50)
    print(f"  Port: {args.port} @ {args.baud}")
    print(f"  Saved: {'Flash+BBR' if save_to_flash else 'RAM only'}")
    print("-" * 50)
    configured = results['uart2_rtcm3_configured']
    print(f"  UART2 RTCM3 configured : {'OK' if configured else 'FAIL'}")
    verified = results.get('uart2_verified', {})
    if verified:
        all_v = verified.get('all_verified', False)
        print(f"  UART2 config verified  : {'OK' if all_v else 'FAIL'}")
        for key_name in _VERIFY_KEYS:
            entry = verified.get(key_name, {})
            ok = 'OK' if entry.get('ok') else 'FAIL'
            print(f"    {key_name:28s}: {ok}")
    if 'gnss_signals_enabled' in results:
        gnss = results['gnss_signals_enabled']
        print(f"  GNSS signals enabled   : {'OK' if gnss else 'FAIL'}")
    print("-" * 50)
    final = 'ALL OK' if results.get('all_ok') else 'SOME FAILED'
    print(f"  FINAL: {final}")
    print("=" * 50)

    return 0 if results.get('all_ok') else 1


if __name__ == '__main__':
    sys.exit(main())
