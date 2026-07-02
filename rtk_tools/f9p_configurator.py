#!/usr/bin/env python3
"""
F9P Configurator - F9P 基地局モード設定クラス

pyubx2 の CFG-VALSET / CFG-VALGET (config_poll) 方式を使用して
u-blox F9P を基地局（Base Station）モードに設定します。

使用例:
    config = {
        "serial_port": "/dev/tty.usbmodem113301",
        "baudrate": 38400,
        "fixed_lat": 35.681236,
        "fixed_lon": 139.767125,
        "fixed_alt": 42.0,
        "save_to_flash": True,
    }
    f9p = F9pConfigurator(config)
    f9p.set_tmode3_fixed()
    f9p.enable_rtcm_output()
    f9p.check_tmode3()
    f9p.close()
"""

import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import serial
from pyubx2 import UBXMessage, UBXReader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
_WGS84_A = 6378137.0
_WGS84_F = 1.0 / 298.257223563
_WGS84_E2 = _WGS84_F * (2.0 - _WGS84_F)

LAYER_RAM = 0x01
LAYER_FLASH = 0x04
LAYER_RAM_FLASH = 0x05

TMODE_DISABLED = 0
TMODE_FIXED = 2
POS_TYPE_ECEF = 0

_RTCM_MESSAGES: List[Tuple[str, int, str]] = [
    ("TYPE1005", 5, "RTCM 1005 (5秒毎)"),
    ("TYPE1077", 1, "RTCM 1077 GPS MSM7"),
    ("TYPE1087", 1, "RTCM 1087 GLONASS MSM7"),
    ("TYPE1097", 1, "RTCM 1097 Galileo MSM7"),
    ("TYPE1127", 1, "RTCM 1127 BeiDou MSM7"),
    ("TYPE1230", 5, "RTCM 1230 GLOバイアス (5秒毎)"),
]

_TMODE3_KEYS: List[str] = [
    "CFG_TMODE_MODE",
    "CFG_TMODE_POS_TYPE",
    "CFG_TMODE_LAT",
    "CFG_TMODE_LON",
    "CFG_TMODE_HEIGHT",
    "CFG_TMODE_ECEF_X",
    "CFG_TMODE_ECEF_Y",
    "CFG_TMODE_ECEF_Z",
    "CFG_TMODE_FIXED_POS_ACC",
]


class F9pConfigurator:
    """F9P 基地局モード設定クラス

    pyubx2 の CFG-VALSET 方式で F9P の TMODE3 Fixed Mode と
    RTCM3 出力メッセージを設定する。
    """

    def __init__(self, config_dict: Dict[str, Any]) -> None:
        """
        Args:
            config_dict:
                serial_port  : str  シリアルポートパス
                baudrate     : int  ボーレート (デフォルト 38400)
                fixed_lat    : float 基地局の固定緯度 [度, WGS84]
                fixed_lon    : float 基地局の固定経度 [度, WGS84]
                fixed_alt    : float 基地局の楕円体高 [m, WGS84]
                save_to_flash: bool Flash 保存有無 (デフォルト True)
        """
        self._serial_port: str = config_dict["serial_port"]
        self._baudrate: int = config_dict.get("baudrate", 38400)
        self._fixed_lat: float = config_dict.get("fixed_lat", 0.0)
        self._fixed_lon: float = config_dict.get("fixed_lon", 0.0)
        self._fixed_alt: float = config_dict.get("fixed_alt", 0.0)
        self._save_to_flash: bool = config_dict.get("save_to_flash", True)
        self._ser: Optional[serial.Serial] = None

    # ------------------------------------------------------------------
    # シリアルポート管理
    # ------------------------------------------------------------------

    def _open_serial(self) -> serial.Serial:
        """シリアルポートを開く（未接続の場合のみ）"""
        if self._ser is not None and self._ser.is_open:
            return self._ser
        logger.info("シリアルポートを開きます: %s @ %d baud",
                     self._serial_port, self._baudrate)
        try:
            self._ser = serial.Serial(
                port=self._serial_port,
                baudrate=self._baudrate,
                timeout=1.0,
            )
            logger.info("シリアルポート接続成功: %s", self._serial_port)
            return self._ser
        except (serial.SerialException, OSError) as exc:
            logger.error("シリアルポートオープン失敗: %s", exc)
            raise

    def close(self) -> None:
        """シリアルポートを閉じる"""
        if self._ser is not None and self._ser.is_open:
            self._ser.close()
            logger.info("シリアルポートをクローズしました: %s",
                        self._serial_port)
        self._ser = None

    # ------------------------------------------------------------------
    # 低レベル UBX 通信
    # ------------------------------------------------------------------

    def _send_ubx_and_wait_ack(
        self, packet: bytes, label: str, timeout: float = 2.0,
    ) -> bool:
        """UBX パケットを送信し ACK/NAK を待つ

        Returns:
            True: ACK受信, False: NAK受信またはタイムアウト
        """
        ser = self._open_serial()
        ser.reset_input_buffer()
        ser.write(packet)
        deadline = time.time() + timeout
        buf = b""
        while time.time() < deadline:
            waiting = ser.in_waiting
            buf += ser.read(waiting if waiting else 1)
            ack_idx = buf.find(b"\xb5\x62\x05\x01")
            if ack_idx != -1 and len(buf) >= ack_idx + 8:
                logger.debug("[ACK] %s", label)
                return True
            nak_idx = buf.find(b"\xb5\x62\x05\x00")
            if nak_idx != -1 and len(buf) >= nak_idx + 8:
                logger.warning("[NAK] %s", label)
                return False
        logger.warning("[TIMEOUT] ACK未受信: %s", label)
        return False

    def _send_cfg_set(
        self, cfg_data: List[Tuple[str, int]], label: str,
        layers: int = LAYER_RAM_FLASH,
    ) -> bool:
        """CFG-VALSET 方式で設定を送信

        Args:
            cfg_data: [(key, value), ...] のリスト
            label: ログ用ラベル
            layers: 書き込み先レイヤー (デフォルト: RAM+FLASH)
        """
        msg = UBXMessage.config_set(
            layers=layers, transaction=0, cfgData=cfg_data,
        )
        packet = msg.serialize()
        return self._send_ubx_and_wait_ack(packet, label, timeout=2.0)

    # ------------------------------------------------------------------
    # LLH → ECEF 変換
    # ------------------------------------------------------------------

    @staticmethod
    def _llh_to_ecef(
        lat_deg: float, lon_deg: float, alt_m: float,
    ) -> Tuple[int, int, int]:
        """WGS84 緯度・経度・楕円体高 → ECEF (cm 単位)

        F9P の CFG-TMODE-ECEF_X/Y/Z は cm 単位のため、
        Python 側で正確に計算して内部変換誤差を回避する。
        """
        lat_rad = math.radians(lat_deg)
        lon_rad = math.radians(lon_deg)
        sin_lat = math.sin(lat_rad)
        cos_lat = math.cos(lat_rad)
        cos_lon = math.cos(lon_rad)
        sin_lon = math.sin(lon_rad)
        N = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)
        ecef_x = int((N + alt_m) * cos_lat * cos_lon * 100)
        ecef_y = int((N + alt_m) * cos_lat * sin_lon * 100)
        ecef_z = int((N * (1.0 - _WGS84_E2) + alt_m) * sin_lat * 100)
        return ecef_x, ecef_y, ecef_z

    # ------------------------------------------------------------------
    # TMODE3 Fixed Mode 設定
    # ------------------------------------------------------------------

    def set_tmode3_fixed(self) -> bool:
        """TMODE3 Fixed Mode を設定する

        1. TMODE3 を Disabled にリセット
        2. タイムモードを Fixed (2) に設定
        3. 座標系を ECEF (0) に指定
        4. ECEF 座標と位置精度を設定
        5. 3 秒の安定化待機

        Returns:
            True: 全ステップ成功
        """
        layers = LAYER_RAM_FLASH if self._save_to_flash else LAYER_RAM
        layer_name = "RAM+FLASH" if layers == LAYER_RAM_FLASH else "RAM"

        logger.info("=" * 60)
        logger.info("[set_tmode3_fixed] TMODE3 Fixed Mode 設定開始")
        logger.info("  緯度: %.7f deg", self._fixed_lat)
        logger.info("  経度: %.7f deg", self._fixed_lon)
        logger.info("  高度: %.3f m (楕円体高)", self._fixed_alt)
        logger.info("  保存先: %s", layer_name)

        # 1. TMODE3 を Disabled にリセット
        logger.info("  -> TMODE3 を Disabled にリセット...")
        ok_reset = self._send_cfg_set(
            [("CFG_TMODE_MODE", TMODE_DISABLED)],
            "TMODE3 Disabled (リセット)",
            layers=layers,
        )
        time.sleep(1.0)

        # 2. タイムモードを Fixed (2) に設定
        ok_mode = self._send_cfg_set(
            [("CFG_TMODE_MODE", TMODE_FIXED)],
            "TMODE3 Fixed Mode (CFG_TMODE_MODE=2)",
            layers=layers,
        )
        time.sleep(0.1)

        # 3. LLH → ECEF 変換
        ecef_x, ecef_y, ecef_z = self._llh_to_ecef(
            self._fixed_lat, self._fixed_lon, self._fixed_alt,
        )
        logger.info(
            "  ECEF X: %.4f m (%d cm)  Y: %.4f m (%d cm)  Z: %.4f m (%d cm)",
            ecef_x / 100.0, ecef_x,
            ecef_y / 100.0, ecef_y,
            ecef_z / 100.0, ecef_z,
        )

        # 4. 座標系を ECEF (0) に指定
        ok_pos_type = self._send_cfg_set(
            [("CFG_TMODE_POS_TYPE", POS_TYPE_ECEF)],
            "TMODE3 POS_TYPE=ECEF",
            layers=layers,
        )
        time.sleep(0.1)

        # 5. ECEF 座標と精度を設定
        ok_ecef = self._send_cfg_set(
            [
                ("CFG_TMODE_ECEF_X", ecef_x),
                ("CFG_TMODE_ECEF_Y", ecef_y),
                ("CFG_TMODE_ECEF_Z", ecef_z),
                ("CFG_TMODE_FIXED_POS_ACC", 100),
            ],
            "TMODE3 ECEF座標設定 (X/Y/Z/Acc)",
            layers=layers,
        )
        time.sleep(0.5)

        # 6. 安定化待機
        logger.info("  -> TMODE3 安定待ち (3秒)...")
        time.sleep(3.0)
        try:
            self._ser.reset_input_buffer()
        except (serial.SerialException, AttributeError):
            pass

        all_ok = ok_reset and ok_mode and ok_pos_type and ok_ecef
        if all_ok:
            logger.info("[set_tmode3_fixed] 設定完了 (全ACK受信)")
        else:
            logger.warning(
                "[set_tmode3_fixed] 一部ACK未受信 "
                "(reset=%s mode=%s pos_type=%s ecef=%s)",
                ok_reset, ok_mode, ok_pos_type, ok_ecef,
            )
        return all_ok

    # ------------------------------------------------------------------
    # RTCM3 出力メッセージ有効化
    # ------------------------------------------------------------------

    def enable_rtcm_output(self) -> bool:
        """RTCM3 出力メッセージを有効化する（UART1 + USB）

        - RTCM 1005: 5 秒毎 (基準局座標)
        - RTCM 1077: 1 秒毎 (GPS MSM7)
        - RTCM 1087: 1 秒毎 (GLONASS MSM7)
        - RTCM 1097: 1 秒毎 (Galileo MSM7)
        - RTCM 1127: 1 秒毎 (BeiDou MSM7)
        - RTCM 1230: 5 秒毎 (GLONASS バイアス情報)
        """
        layers = LAYER_RAM_FLASH if self._save_to_flash else LAYER_RAM
        logger.info("=" * 60)
        logger.info("[enable_rtcm_output] RTCM3 出力メッセージ有効化")

        all_ok = True
        for suffix, rate, desc in _RTCM_MESSAGES:
            cfg_key = f"CFG_MSGOUT_RTCM_3X_{suffix}"

            ok_uart = self._send_cfg_set(
                [(f"{cfg_key}_UART1", rate)],
                f"{desc} (UART1)",
                layers=layers,
            )
            time.sleep(0.05)

            ok_usb = self._send_cfg_set(
                [(f"{cfg_key}_USB", rate)],
                f"{desc} (USB)",
                layers=layers,
            )
            time.sleep(0.05)

            if not ok_uart or not ok_usb:
                all_ok = False
                logger.warning(
                    "  RTCM出力エラー: %s (UART1=%s USB=%s)",
                    desc, ok_uart, ok_usb,
                )

        if all_ok:
            logger.info("[enable_rtcm_output] 全RTCMメッセージ有効化完了")
            if self._save_to_flash:
                logger.info(
                    "  -> 設定は RAM+FLASH に保存 (電源OFF後も保持)"
                )
        else:
            logger.warning(
                "[enable_rtcm_output] 一部のRTCMメッセージ設定に失敗"
            )
        return all_ok


    # ------------------------------------------------------------------
    # TMODE3 読み取り (config_poll)
    # ------------------------------------------------------------------

    def check_tmode3(self, timeout: float = 2.0) -> Optional[Dict[str, int]]:
        """現在の TMODE3 設定を config_poll() で読み取る

        pyubx2 の config_poll() は CFG-VALGET poll リクエストを送信し、
        デバイスから CFG-VALGET 応答として現在の設定値を返す。
        (古い config_get() からの移行)

        Returns:
            設定辞書 (キー名 → 値)、読み取り失敗時は None
        """
        logger.info("=" * 60)
        logger.info("[check_tmode3] 現在の TMODE3 設定を読み取り")

        ser = self._open_serial()
        poll_msg = UBXMessage.config_poll(
            layer=LAYER_RAM, position=0, keys=_TMODE3_KEYS,
        )
        ser.reset_input_buffer()
        ser.write(poll_msg.serialize())

        ubr = UBXReader(ser)
        deadline = time.time() + timeout
        result: Optional[Dict[str, int]] = None

        while time.time() < deadline:
            try:
                raw, parsed = ubr.read()
                if raw is None:
                    time.sleep(0.05)
                    continue

                ident = getattr(parsed, "identity", None)
                if ident == "CFG-VALGET":
                    result = {}
                    logger.info("  CFG-VALGET 応答を受信:")
                    skip_attrs = {
                        "identity", "payload", "transport",
                        "msg_cls", "msg_id", "length", "checksum",
                    }
                    for attr in dir(parsed):
                        if attr.startswith("_") or attr in skip_attrs:
                            continue
                        try:
                            val = getattr(parsed, attr)
                            if val is not None and not callable(val):
                                result[attr] = val
                                logger.info("    %s = %s", attr, val)
                        except Exception:
                            pass
                    break

            except Exception as exc:
                logger.debug("  UBXReader parse error: %s", exc)
                continue

        if result is None:
            logger.warning(
                "[check_tmode3] CFG-VALGET 応答を取得できませんでした"
            )
        else:
            logger.info(
                "[check_tmode3] 読み取り完了 (%d 項目)", len(result)
            )
        return result

    # ------------------------------------------------------------------
    # コンテキストマネージャ
    # ------------------------------------------------------------------

    def __enter__(self) -> "F9pConfigurator":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

