#!/usr/bin/env python3
"""
f9p_config_all.py — DroneCAN F9P (NEO-F9P) 全設定値の「書き込み→確認」ツール

基地局・移動局の F9P 全30設定キーを単一スクリプトで管理する。
pyubx2 の UBXMessage.config_set() / config_poll() (CFG-VALSET / CFG-VALGET) を使用。

Reference:
  - rtk_tools/f9p_configurator.py    (Base station config pattern)
  - rtk_tools/f9p_rover_config.py    (Rover config pattern)
  - rtk_tools/f9p_verify_config.py   (Verification pattern)
"""

import argparse
import json
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import serial
from pyubx2 import UBXMessage

# ==========================================================================
# Layer bitmask for config_set
# ==========================================================================
LAYER_RAM   = 1
LAYER_BBR   = 2
LAYER_FLASH = 4
LAYER_ALL   = LAYER_RAM | LAYER_BBR | LAYER_FLASH

# UBX-MON-VER poll request
_MON_VER_POLL = bytes([0xB5, 0x62, 0x0A, 0x04, 0x00, 0x00, 0x0E, 0x34])

# CFG-VALGET retry config
_MAX_RETRIES = 3
_TIMEOUT = 5.0

# Display icons
_ICON_OK   = "\u2705"
_ICON_FAIL = "\u274c"
_ICON_WARN = "\u26a0\ufe0f"

# ==========================================================================
# CFG Key ID mapping for response parsing
# ==========================================================================
_KEY_TMODE_MODE           = 0x20030001
_KEY_TMODE_POS_TYPE       = 0x20030002
_KEY_TMODE_LAT            = 0x40030009
_KEY_TMODE_LON            = 0x4003000A
_KEY_TMODE_HEIGHT         = 0x4003000B
_KEY_UART1_BAUDRATE       = 0x40520001
_KEY_UART1OUTPROT_UBX     = 0x40520005
_KEY_UART2_BAUDRATE       = 0x40590001
_KEY_UART2INPROT_UBX      = 0x40590002
_KEY_UART2INPROT_NMEA     = 0x40590003
_KEY_UART2INPROT_RTCM3X   = 0x40590004
_KEY_UART2OUTPROT_UBX     = 0x40590005
_KEY_UART2OUTPROT_NMEA    = 0x40590006
_KEY_NAVHPG_DGNSSMODE     = 0x20110011
_KEY_RATE_MEAS            = 0x30210001
_KEY_RATE_NAV             = 0x30210002
_KEY_MSGOUT_UBX_NAV_PVT_UART2 = 0x20910006

_U4_KEY_IDS = {_KEY_UART1_BAUDRATE, _KEY_UART2_BAUDRATE}
_I4_KEY_IDS = {_KEY_TMODE_LAT, _KEY_TMODE_LON, _KEY_TMODE_HEIGHT}
_U2_KEY_IDS = {_KEY_RATE_MEAS, _KEY_RATE_NAV}

# ==========================================================================
# Full 30-key Configuration Table
# ==========================================================================

def _build_key_table(lat: float, lon: float, alt: float) -> List[dict]:
    """Build the full 30-key configuration table with resolved dynamic values."""
    lat_e7 = int(lat * 1e7)
    lon_e7 = int(lon * 1e7)
    alt_cm = int(alt * 100)

    return [
        # === Base Station (12 keys: #1-12) ===
        {"id": 1, "key": "CFG-TMODE-MODE",
         "expected": 2, "type": "U1", "role": "base",
         "desc": "FIXED Mode (2=Fixed)", "key_id": _KEY_TMODE_MODE},
        {"id": 2, "key": "CFG-TMODE-POS_TYPE",
         "expected": 0, "type": "U1", "role": "base",
         "desc": "Position type (0=LLA)", "key_id": _KEY_TMODE_POS_TYPE},
        {"id": 3, "key": "CFG-TMODE-LAT",
         "expected": lat_e7, "type": "I4", "role": "base",
         "desc": f"Lat ({lat:.7f} deg)", "key_id": _KEY_TMODE_LAT},
        {"id": 4, "key": "CFG-TMODE-LON",
         "expected": lon_e7, "type": "I4", "role": "base",
         "desc": f"Lon ({lon:.7f} deg)", "key_id": _KEY_TMODE_LON},
        {"id": 5, "key": "CFG-TMODE-HEIGHT",
         "expected": alt_cm, "type": "I4", "role": "base",
         "desc": f"Height ({alt:.1f}m)", "key_id": _KEY_TMODE_HEIGHT},
        {"id": 6, "key": "CFG-MSGOUT-RTCM_3X_TYPE1005_UART1",
         "expected": 1, "type": "U1", "role": "base",
         "desc": "Station ARP (1005)", "key_id": None},
        {"id": 7, "key": "CFG-MSGOUT-RTCM_3X_TYPE1006_UART1",
         "expected": 1, "type": "U1", "role": "base",
         "desc": "Station ARP+Ant (1006)", "key_id": None},
        {"id": 8, "key": "CFG-MSGOUT-RTCM_3X_TYPE1074_UART1",
         "expected": 1, "type": "U1", "role": "base",
         "desc": "GPS MSM4 (1074)", "key_id": None},
        {"id": 9, "key": "CFG-MSGOUT-RTCM_3X_TYPE1084_UART1",
         "expected": 1, "type": "U1", "role": "base",
         "desc": "GLONASS MSM4 (1084)", "key_id": None},
        {"id": 10, "key": "CFG-MSGOUT-RTCM_3X_TYPE1094_UART1",
         "expected": 1, "type": "U1", "role": "base",
         "desc": "Galileo MSM4 (1094)", "key_id": None},
        {"id": 11, "key": "CFG-MSGOUT-RTCM_3X_TYPE1124_UART1",
         "expected": 1, "type": "U1", "role": "base",
         "desc": "BeiDou MSM4 (1124)", "key_id": None},
        {"id": 12, "key": "CFG-MSGOUT-RTCM_3X_TYPE1230_UART1",
         "expected": 1, "type": "U1", "role": "base",
         "desc": "GLONASS bias (1230)", "key_id": None},

        # === Rover (18 keys: #13-30) ===
        {"id": 13, "key": "CFG-UART2-BAUDRATE",
         "expected": 115200, "type": "U4", "role": "rover",
         "desc": "UART2 baudrate", "key_id": _KEY_UART2_BAUDRATE},
        {"id": 14, "key": "CFG-UART2INPROT-UBX",
         "expected": 1, "type": "U1", "role": "rover",
         "desc": "UBX input enabled (RTCM3+UBX mixed)", "key_id": _KEY_UART2INPROT_UBX},
        {"id": 15, "key": "CFG-UART2INPROT-NMEA",
         "expected": 0, "type": "U1", "role": "rover",
         "desc": "NMEA input disabled", "key_id": _KEY_UART2INPROT_NMEA},
        {"id": 16, "key": "CFG-UART2INPROT-RTCM3X",
         "expected": 1, "type": "U1", "role": "rover",
         "desc": "RTCM3 input enabled", "key_id": _KEY_UART2INPROT_RTCM3X},
        {"id": 17, "key": "CFG-UART2OUTPROT-UBX",
         "expected": 0, "type": "U1", "role": "rover",
         "desc": "UBX output disabled", "key_id": _KEY_UART2OUTPROT_UBX},
        {"id": 18, "key": "CFG-UART2OUTPROT-NMEA",
         "expected": 0, "type": "U1", "role": "rover",
         "desc": "NMEA output disabled", "key_id": _KEY_UART2OUTPROT_NMEA},
        {"id": 19, "key": "CFG-NAVHPG-DGNSSMODE",
         "expected": 3, "type": "U1", "role": "rover",
         "desc": "RTK Fixed (3=RTK Fixed)", "key_id": _KEY_NAVHPG_DGNSSMODE},
        {"id": 20, "key": "CFG-RATE-MEAS",
         "expected": 200, "type": "U2", "role": "rover",
         "desc": "Meas period 200ms (5Hz)", "key_id": _KEY_RATE_MEAS},
        {"id": 21, "key": "CFG-RATE-NAV",
         "expected": 1, "type": "U2", "role": "rover",
         "desc": "Nav output ratio 1:1", "key_id": _KEY_RATE_NAV},
        {"id": 22, "key": "CFG-MSGOUT-UBX-NAV-PVT-UART2",
         "expected": 0, "type": "U1", "role": "rover",
         "desc": "NAV-PVT UART2 out disabled",
         "key_id": _KEY_MSGOUT_UBX_NAV_PVT_UART2},
        {"id": 23, "key": "CFG-SIGNAL-GPS_ENA",
         "expected": 1, "type": "U1", "role": "rover",
         "desc": "GPS L1C/A enabled", "key_id": None},
        {"id": 24, "key": "CFG-SIGNAL-GPS_L5_ENA",
         "expected": 1, "type": "U1", "role": "rover",
         "desc": "GPS L5 enabled", "key_id": None},
        {"id": 25, "key": "CFG-SIGNAL-GAL_ENA",
         "expected": 1, "type": "U1", "role": "rover",
         "desc": "Galileo E1 enabled", "key_id": None},
        {"id": 26, "key": "CFG-SIGNAL-GAL_E5A_ENA",
         "expected": 1, "type": "U1", "role": "rover",
         "desc": "Galileo E5a enabled", "key_id": None},
        {"id": 27, "key": "CFG-SIGNAL-BDS_ENA",
         "expected": 1, "type": "U1", "role": "rover",
         "desc": "BeiDou B1I enabled", "key_id": None},
        {"id": 28, "key": "CFG-SIGNAL-GLO_ENA",
         "expected": 1, "type": "U1", "role": "rover",
         "desc": "GLONASS L1 enabled", "key_id": None},
        {"id": 29, "key": "CFG-UART1OUTPROT-UBX",
         "expected": 1, "type": "U1", "role": "rover",
         "desc": "UART1 UBX -> AP_Periph",
         "key_id": _KEY_UART1OUTPROT_UBX},
        {"id": 30, "key": "CFG-UART1-BAUDRATE",
         "expected": 115200, "type": "U4", "role": "rover",
         "desc": "UART1 baudrate", "key_id": _KEY_UART1_BAUDRATE},
    ]


def _get_keys_by_role(keys: List[dict], role: str) -> List[dict]:
    """Filter key table by role."""
    return [k for k in keys if k["role"] == role]


# ==========================================================================
# CFG-VALSET key groups (for write operations)
# ==========================================================================
_RTCM_MSG_KEYS = [
    "CFG-MSGOUT-RTCM_3X_TYPE1005_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1006_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1074_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1084_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1094_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1124_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1230_UART1",
]

_UART2_ROVER_CFG_KEYS = [
    ("CFG-UART2-BAUDRATE",              115200),
    ("CFG-UART2INPROT-UBX",             1),
    ("CFG-UART2INPROT-NMEA",            0),
    ("CFG-UART2INPROT-RTCM3X",          1),
    ("CFG-UART2OUTPROT-UBX",            0),
    ("CFG-UART2OUTPROT-NMEA",           0),
    ("CFG-NAVHPG-DGNSSMODE",            3),
    ("CFG-RATE-MEAS",                   200),
    ("CFG-RATE-NAV",                    1),
    ("CFG-MSGOUT-UBX-NAV-PVT-UART2",    0),
]

_GNSS_SIGNAL_CFG_KEYS = [
    ("CFG-SIGNAL-GPS_ENA",     1),
    ("CFG-SIGNAL-GPS_L5_ENA",  1),
    ("CFG-SIGNAL-GAL_ENA",     1),
    ("CFG-SIGNAL-GAL_E5A_ENA", 1),
    ("CFG-SIGNAL-BDS_ENA",     1),
    ("CFG-SIGNAL-GLO_ENA",     1),
]


# ==========================================================================
# F9pAllConfigurator
# ==========================================================================

class F9pAllConfigurator:
    """DroneCAN F9P (NEO-F9P) 全設定値の書き込みと確認を行う。"""

    def __init__(self, serial_port: str, baudrate: int = 38400,
                 logger: Optional[logging.Logger] = None):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.logger = logger or logging.getLogger("F9pAllConfigurator")
        self._ser: Optional[serial.Serial] = None

    # ------------------------------------------------------------------
    # Serial I/O (pattern from f9p_configurator.py)
    # ------------------------------------------------------------------

    def _open_serial(self) -> serial.Serial:
        self.logger.info(
            f"Opening serial port: {self.serial_port} @ {self.baudrate}"
        )
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
        """指定された Class/ID の UBX 応答を raw byte search で読み取る。

        UBXReader ではなく raw serial read + UBX sync pattern (0xB5 0x62)
        検索を使用する。これにより RTCM3 ストリーム (0xD3 sync) と UBX フレームが
        混在する低ボーレート環境（38400bps など）でも堅牢に UBX 応答を検出できる。
        """
        if not self._ser or not self._ser.is_open:
            return None

        deadline = time.time() + timeout
        buf = b''

        while time.time() < deadline:
            # Read whatever is available
            waiting = self._ser.in_waiting
            if waiting > 0:
                chunk = self._ser.read(waiting)
                buf += chunk

            # Scan for UBX sync pattern 0xB5 0x62
            idx = 0
            while True:
                sync_pos = buf.find(b'\xb5\x62', idx)
                if sync_pos < 0:
                    # Keep trailing byte if it could be partial sync (0xB5)
                    if len(buf) > 0 and buf[-1:] == b'\xb5':
                        buf = b'\xb5'
                    elif len(buf) > 0:
                        buf = b''
                    break  # need more data

                # Need at least 6 header bytes after sync (CLASS,ID,LEN_L,LEN_H)
                if sync_pos + 6 > len(buf):
                    buf = buf[sync_pos:]
                    break

                frame_cls = buf[sync_pos + 2]
                frame_id = buf[sync_pos + 3]
                payload_len = buf[sync_pos + 4] | (buf[sync_pos + 5] << 8)

                # Total frame: SYNC(2)+CLASS(1)+ID(1)+LEN(2)+PAYLOAD+CHK(2)
                total_len = 8 + payload_len

                if sync_pos + total_len > len(buf):
                    # Incomplete frame; keep from sync_pos
                    buf = buf[sync_pos:]
                    break

                # Extract candidate frame
                frame = buf[sync_pos:sync_pos + total_len]

                # Verify UBX checksum (8-bit Fletcher over CLASS..PAYLOAD_END)
                ck_a = 0
                ck_b = 0
                for b in frame[2:6 + payload_len]:
                    ck_a = (ck_a + b) & 0xFF
                    ck_b = (ck_b + ck_a) & 0xFF

                expected_ck_a = frame[6 + payload_len]
                expected_ck_b = frame[6 + payload_len + 1]

                if ck_a == expected_ck_a and ck_b == expected_ck_b:
                    # Valid UBX frame
                    if frame_cls == cls and frame_id == mid:
                        return frame
                    # Not the frame we want; skip this frame
                    idx = sync_pos + total_len
                else:
                    # Corrupt frame; skip past sync
                    idx = sync_pos + 2

            if not self._ser.in_waiting:
                time.sleep(0.01)

        return None

    def _check_device_alive(self) -> bool:
        """UBX-MON-VER ポーリングで F9P の生存を確認する"""
        if not self._ser or not self._ser.is_open:
            return False
        try:
            self._ser.reset_input_buffer()
            self._send_ubx(_MON_VER_POLL)
            raw = self._read_ubx_response(0x0A, 0x04, timeout=3.0)
            if raw and len(raw) >= 8:
                self.logger.info("Device alive OK")
                return True
            self.logger.warning("Device alive: no MON-VER response")
            return False
        except Exception as e:
            self.logger.error(f"Device alive check failed: {e}")
            return False

    def _poll_config(self, keys: List[str],
                     timeout: float = _TIMEOUT,
                     max_retries: int = _MAX_RETRIES) -> Optional[bytes]:
        """CFG-VALGET ポーリング（リトライ付き）"""
        for attempt in range(1, max_retries + 1):
            poll_msg = UBXMessage.config_poll(0, 0, keys)
            self._ser.reset_input_buffer()
            self._send_ubx(poll_msg.serialize())
            raw = self._read_ubx_response(0x06, 0x8B, timeout=timeout)
            if raw and len(raw) >= 10:
                return raw
            if attempt < max_retries:
                time.sleep(0.5)
        self.logger.warning(
            f"No CFG-VALGET after {max_retries} attempts"
        )
        return None

    def _parse_single_valget(self, raw: bytes) -> Tuple[int, Any]:
        """Parse single-key CFG-VALGET response -> (key_id, value).

        Payload: [version:1][layer:1][position:2][key:4][value:var]
        """
        payload = raw[6:-2]
        if len(payload) < 8:
            return 0, None
        key_id = int.from_bytes(payload[4:8], "little")
        value_start = 8
        if key_id in _U4_KEY_IDS:
            if len(payload) >= value_start + 4:
                value = int.from_bytes(
                    payload[value_start:value_start + 4], "little")
            else:
                value = None
        elif key_id in _I4_KEY_IDS:
            if len(payload) >= value_start + 4:
                value = int.from_bytes(
                    payload[value_start:value_start + 4],
                    "little", signed=True)
            else:
                value = None
        elif key_id in _U2_KEY_IDS:
            if len(payload) >= value_start + 2:
                value = int.from_bytes(
                    payload[value_start:value_start + 2], "little")
            else:
                value = None
        else:
            if len(payload) >= value_start + 1:
                value = payload[value_start]
            else:
                value = None
        return key_id, value

    def _verify_single_key(self, key_name: str, expected: Any) -> dict:
        """Poll a single config key and return verification result dict."""
        result = {
            "key": key_name, "expected": expected, "actual": None,
            "status": "fail", "icon": _ICON_FAIL, "suggestion": "",
        }
        if not self._ser or not self._ser.is_open:
            result["suggestion"] = "Serial port not open"
            return result
        raw = self._poll_config([key_name], timeout=3.0, max_retries=2)
        if raw is None or len(raw) < 14:
            result["status"] = "warn"
            result["icon"] = _ICON_WARN
            result["actual"] = "No response"
            result["suggestion"] = f"F9P not responding for {key_name}."
            return result
        _key_id, value = self._parse_single_valget(raw)
        result["actual"] = value
        if value is not None and value == expected:
            result["status"] = "ok"
            result["icon"] = _ICON_OK
        elif value is None:
            result["status"] = "warn"
            result["icon"] = _ICON_WARN
            result["actual"] = "Parse error"
            result["suggestion"] = f"Failed to parse {key_name} value."
        else:
            result["suggestion"] = (
                f"{key_name}: actual={value}, expected={expected}"
            )
        return result

    # ------------------------------------------------------------------
    # Write: Base Station
    # ------------------------------------------------------------------

    def write_base_tmode3(self, lat: float, lon: float, alt: float,
                           save_to_flash: bool = True) -> bool:
        """STEP1: TMODE3 Fixed Mode 設定 (CFG-VALSET)"""
        self._ser = self._open_serial()
        try:
            lat_e7 = int(lat * 1e7)
            lon_e7 = int(lon * 1e7)
            alt_cm = int(alt * 100)
            cfg_data = [
                ("CFG-TMODE-MODE", 2),
                ("CFG-TMODE-POS_TYPE", 0),
                ("CFG-TMODE-LAT", lat_e7),
                ("CFG-TMODE-LON", lon_e7),
                ("CFG-TMODE-HEIGHT", alt_cm),
            ]
            layers = LAYER_ALL if save_to_flash else LAYER_RAM
            msg = UBXMessage.config_set(layers, 0, cfg_data)
            self._send_ubx(msg.serialize())
            self.logger.info(
                f"[BASE Write] TMODE3 Fixed: "
                f"lat={lat:.7f} lon={lon:.7f} alt={alt:.1f}m "
                f"({'Flash' if save_to_flash else 'RAM'})"
            )
            if save_to_flash:
                time.sleep(0.5)
            return True
        except Exception as e:
            self.logger.error(f"[BASE Write] TMODE3 failed: {e}")
            return False
        finally:
            self._close_serial()

    def write_base_rtcm3(self, save_to_flash: bool = True) -> bool:
        """STEP2: RTCM3 出力メッセージ有効化 (CFG-VALSET)"""
        self._ser = self._open_serial()
        try:
            cfg_data = [(k, 1) for k in _RTCM_MSG_KEYS]
            layers = LAYER_ALL if save_to_flash else LAYER_RAM
            msg = UBXMessage.config_set(layers, 0, cfg_data)
            self._send_ubx(msg.serialize())
            self.logger.info(
                f"[BASE Write] RTCM3: {len(_RTCM_MSG_KEYS)} msgs "
                f"({'Flash' if save_to_flash else 'RAM'})"
            )
            if save_to_flash:
                time.sleep(0.5)
            return True
        except Exception as e:
            self.logger.error(f"[BASE Write] RTCM3 failed: {e}")
            return False
        finally:
            self._close_serial()

    # ------------------------------------------------------------------
    # Write: Rover
    # ------------------------------------------------------------------

    def write_rover_uart2(self, save_to_flash: bool = True) -> bool:
        """STEP1: Rover UART2 + Rate + DGNSS 設定 (CFG-VALSET)"""
        self._ser = self._open_serial()
        try:
            layers = LAYER_ALL if save_to_flash else LAYER_RAM
            cfg_data = list(_UART2_ROVER_CFG_KEYS)
            msg = UBXMessage.config_set(layers, 0, cfg_data)
            self._send_ubx(msg.serialize())
            self.logger.info(
                f"[ROVER Write] UART2+Rate: {len(cfg_data)} keys "
                f"({'Flash' if save_to_flash else 'RAM'})"
            )
            if save_to_flash:
                time.sleep(0.5)
            return True
        except Exception as e:
            self.logger.error(f"[ROVER Write] UART2 failed: {e}")
            return False
        finally:
            self._close_serial()

    def write_rover_gnss(self, save_to_flash: bool = True) -> bool:
        """STEP2: GNSS signals + UART1 output 設定 (CFG-VALSET)"""
        self._ser = self._open_serial()
        try:
            layers = LAYER_ALL if save_to_flash else LAYER_RAM
            cfg_data = list(_GNSS_SIGNAL_CFG_KEYS) + [
                ("CFG-UART1OUTPROT-UBX", 1),
                ("CFG-UART1-BAUDRATE", 115200),
            ]
            msg = UBXMessage.config_set(layers, 0, cfg_data)
            self._send_ubx(msg.serialize())
            self.logger.info(
                f"[ROVER Write] GNSS+UART1: {len(cfg_data)} keys "
                f"({'Flash' if save_to_flash else 'RAM'})"
            )
            if save_to_flash:
                time.sleep(0.5)
            return True
        except Exception as e:
            self.logger.error(f"[ROVER Write] GNSS failed: {e}")
            return False
        finally:
            self._close_serial()

    # ------------------------------------------------------------------
    # Verify: Full role check
    # ------------------------------------------------------------------

    def verify_role(self, role: str, key_table: List[dict]) -> dict:
        """Verify all keys for a given role."""
        role_keys = _get_keys_by_role(key_table, role)
        label = "BASE" if role == "base" else "ROVER"

        summary = {
            "role": role, "port": self.serial_port,
            "device_alive": False, "checks": [],
            "all_verified": False,
            "ok_count": 0, "fail_count": 0, "warn_count": 0,
        }

        self._ser = self._open_serial()
        try:
            alive = self._check_device_alive()
            summary["device_alive"] = alive
            if not alive:
                for k in role_keys:
                    summary["checks"].append({
                        "id": k["id"], "key": k["key"],
                        "description": k["desc"],
                        "expected": k["expected"],
                        "actual": "Device not alive",
                        "status": "warn", "icon": _ICON_WARN,
                        "suggestion": "Check connection/baudrate.",
                    })
                    summary["warn_count"] += 1
                return summary

            self.logger.info(f"[{label} Verify] Polling {len(role_keys)} keys...")
            for k in role_keys:
                r = self._verify_single_key(k["key"], k["expected"])
                r["id"] = k["id"]
                r["description"] = k["desc"]
                summary["checks"].append(r)
                if r["status"] == "ok":
                    summary["ok_count"] += 1
                elif r["status"] == "fail":
                    summary["fail_count"] += 1
                else:
                    summary["warn_count"] += 1
                time.sleep(0.05)

            summary["all_verified"] = (
                summary["fail_count"] == 0 and summary["device_alive"]
            )
        except Exception as e:
            self.logger.error(f"[{label} Verify] Error: {e}")
        finally:
            self._close_serial()

        return summary

    # ------------------------------------------------------------------
    # Unified: Write + Verify
    # ------------------------------------------------------------------

    def write_and_verify(self, role: str, key_table: List[dict],
                         lat: float = 0, lon: float = 0, alt: float = 0,
                         save_to_flash: bool = True) -> dict:
        """Write all config for a role, then verify."""
        write_results: Dict[str, bool] = {}
        label = "BASE" if role == "base" else "ROVER"

        self.logger.info("=" * 60)
        self.logger.info(f"F9P {label}: Write -> Verify")
        self.logger.info(f"  Port: {self.serial_port} @ {self.baudrate}")
        self.logger.info(f"  Save: {'Flash' if save_to_flash else 'RAM'}")
        self.logger.info("=" * 60)

        if role == "base":
            write_results["tmode3"] = self.write_base_tmode3(
                lat, lon, alt, save_to_flash)
            write_results["rtcm3"] = (
                self.write_base_rtcm3(save_to_flash)
                if write_results["tmode3"] else False
            )
        else:
            write_results["uart2"] = self.write_rover_uart2(save_to_flash)
            write_results["gnss_uart1"] = self.write_rover_gnss(
                save_to_flash)

        verify_result = self.verify_role(role, key_table)

        all_ok = (
            all(write_results.values())
            and verify_result.get("all_verified", False)
        )

        return {
            "role": role, "port": self.serial_port,
            "write": write_results, "verify": verify_result,
            "all_ok": all_ok,
        }


# ==========================================================================
# Display helpers
# ==========================================================================

def _print_header(role: str, port: str, mode: str) -> None:
    label = "BASE STATION" if role == "base" else "ROVER"
    print()
    print("=" * 70)
    print(f"  F9P Configuration -- {label}  ({mode.upper()})")
    print(f"  Port: {port}")
    print("=" * 70)
    print()


def _print_key_result(check: dict) -> None:
    icon = check.get("icon", _ICON_WARN)
    kid = check.get("id", "?")
    key = check.get("key", "?")
    desc = check.get("description", "")
    expected = check.get("expected", "?")
    actual = check.get("actual", "?")
    status = check.get("status", "warn")
    labels = {"ok": "OK", "fail": "FAIL", "warn": "WARN"}
    label = labels.get(status, "WARN")
    print(f"  {icon} [{label:4s}] #{kid:2d} {key}")
    print(f"          {desc}")
    print(f"          Expected: {expected!s:<12} Actual: {actual!s}")


def _print_verify_summary(summary: dict) -> None:
    total = summary["ok_count"] + summary["fail_count"] + summary["warn_count"]
    print()
    print("-" * 70)
    print(
        f"  Results:  {_ICON_OK} OK={summary['ok_count']}  "
        f"{_ICON_FAIL} FAIL={summary['fail_count']}  "
        f"{_ICON_WARN} WARN={summary['warn_count']}  "
        f"(total: {total})"
    )
    alive = "YES" if summary.get("device_alive") else "NO"
    verified = "YES" if summary.get("all_verified") else "NO"
    print(f"  Device alive: {alive}")
    print(f"  All verified: {verified}")
    print("-" * 70)
    suggestions = [
        c.get("suggestion", "")
        for c in summary.get("checks", [])
        if c.get("suggestion") and c["status"] in ("fail", "warn")
    ]
    if suggestions:
        print()
        print("  Fix suggestions:")
        for i, s in enumerate(suggestions, 1):
            print(f"    {i}. {s}")


def _print_write_summary(write_results: dict) -> None:
    print()
    print("-" * 70)
    for stage, ok in write_results.items():
        icon = _ICON_OK if ok else _ICON_FAIL
        status = "OK" if ok else "FAIL"
        print(f"  {icon} Write {stage:20s}: {status}")
    all_ok = all(write_results.values())
    print(f"  Write all stages: {'OK' if all_ok else 'FAIL'}")
    print("-" * 70)


# ==========================================================================
# CLI Entry Point
# ==========================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="DroneCAN F9P (NEO-F9P) 全設定値 書込/確認ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --role base --port /dev/tty.usbmodem114301\n"
            "  %(prog)s --role rover --mode verify --port /dev/ttyAMA4\n"
            "  %(prog)s --role both --base-port /dev/tty.X --rover-port /dev/tty.Y\n"
        ),
    )
    parser.add_argument("--role", required=True,
                        choices=["base", "rover", "both"],
                        help="Target role")
    parser.add_argument("--mode", default="write-verify",
                        choices=["write", "verify", "write-verify"],
                        help="Operation mode (default: write-verify)")
    parser.add_argument("--port", default=None,
                        help="Serial port (single role)")
    parser.add_argument("--base-port", default="/dev/tty.usbmodem114301",
                        help="Base port (--role both)")
    parser.add_argument("--rover-port", default="/dev/ttyAMA4",
                        help="Rover port (--role both)")
    parser.add_argument("--baud", type=int, default=None,
                        help="Baudrate (single; defaults: base=38400 rover=115200)")
    parser.add_argument("--base-baud", type=int, default=38400,
                        help="Base baudrate (default: 38400)")
    parser.add_argument("--rover-baud", type=int, default=115200,
                        help="Rover baudrate (default: 115200)")
    parser.add_argument("--lat", type=float, default=35.1234567,
                        help="Base latitude (default: 35.1234567)")
    parser.add_argument("--lon", type=float, default=139.1234567,
                        help="Base longitude (default: 139.1234567)")
    parser.add_argument("--alt", type=float, default=100.0,
                        help="Base altitude in meters (default: 100.0)")
    parser.add_argument("--no-flash", action="store_true",
                        help="Skip Flash save (RAM only)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--log-level", default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Log level (default: WARNING)")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("f9p_config_all")

    base_baud = args.base_baud
    rover_baud = args.rover_baud
    if args.baud is not None:
        if args.role == "base":
            base_baud = args.baud
        elif args.role == "rover":
            rover_baud = args.baud

    key_table = _build_key_table(args.lat, args.lon, args.alt)
    save_to_flash = not args.no_flash

    results: Dict[str, Any] = {}
    exit_code = 0

    roles_to_run: List[str] = []
    if args.role in ("base", "both"):
        roles_to_run.append("base")
    if args.role in ("rover", "both"):
        roles_to_run.append("rover")

    for role in roles_to_run:
        port = args.port if args.role == role else (
            args.base_port if role == "base" else args.rover_port)
        baud = base_baud if role == "base" else rover_baud

        if not port:
            print(f"Error: --port required for --role {role}", file=sys.stderr)
            return 1

        cfg = F9pAllConfigurator(serial_port=port, baudrate=baud, logger=logger)

        if args.mode == "write":
            write_ok: Dict[str, bool] = {}
            if role == "base":
                write_ok["tmode3"] = cfg.write_base_tmode3(
                    args.lat, args.lon, args.alt, save_to_flash)
                write_ok["rtcm3"] = (
                    cfg.write_base_rtcm3(save_to_flash)
                    if write_ok["tmode3"] else False)
            else:
                write_ok["uart2"] = cfg.write_rover_uart2(save_to_flash)
                write_ok["gnss_uart1"] = cfg.write_rover_gnss(save_to_flash)
            results[role] = {
                "role": role, "port": port,
                "write": write_ok, "all_ok": all(write_ok.values()),
            }
            if not results[role]["all_ok"]:
                exit_code = 1

        elif args.mode == "verify":
            cfg._ser = cfg._open_serial()
            verify_result = cfg.verify_role(role, key_table)
            cfg._close_serial()
            results[role] = verify_result
            if not verify_result.get("all_verified"):
                exit_code = 1

        else:  # write-verify
            result = cfg.write_and_verify(
                role, key_table,
                lat=args.lat, lon=args.lon, alt=args.alt,
                save_to_flash=save_to_flash,
            )
            results[role] = result
            if not result.get("all_ok"):
                exit_code = 1

    # --- Output ---
    if args.json:
        output: Dict[str, Any] = {}
        for role in roles_to_run:
            r = results.get(role, {})
            if args.mode == "write":
                output[role] = r
            else:
                summary = r.get("verify", r)
                output[role] = {
                    "role": role, "port": r.get("port", ""),
                    "device_alive": summary.get("device_alive", False),
                    "all_verified": summary.get("all_verified", False),
                    "ok_count": summary.get("ok_count", 0),
                    "fail_count": summary.get("fail_count", 0),
                    "warn_count": summary.get("warn_count", 0),
                    "checks": [
                        {
                            "id": c["id"], "key": c["key"],
                            "description": c.get("description", ""),
                            "expected": c["expected"],
                            "actual": c["actual"],
                            "status": c["status"],
                        }
                        for c in summary.get("checks", [])
                    ],
                }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return exit_code

    # Text output
    for role in roles_to_run:
        r = results[role]
        port = r.get("port", "")
        _print_header(role, port, args.mode)

        if args.mode == "write":
            _print_write_summary(r.get("write", {}))
        else:
            summary = r.get("verify", r)
            device_alive = summary.get("device_alive", False)
            if not device_alive:
                print(f"  {_ICON_FAIL} Device not responding -- cannot verify")
            else:
                for check in summary.get("checks", []):
                    _print_key_result(check)
            _print_verify_summary(summary)
            all_verified = summary.get("all_verified", False)
            icon = _ICON_OK if all_verified else _ICON_FAIL
            label = "BASE" if role == "base" else "ROVER"
            print(f"  {icon} {label}: All verified: {'YES' if all_verified else 'NO'}")

    if len(roles_to_run) == 2:
        print()
        print("=" * 70)
        base_ok = results.get("base", {}).get("all_verified",
            results.get("base", {}).get("all_ok", False))
        rover_ok = results.get("rover", {}).get("all_verified",
            results.get("rover", {}).get("all_ok", False))
        overall_ok = base_ok and rover_ok
        overall_icon = _ICON_OK if overall_ok else _ICON_FAIL
        print(f"  {overall_icon} BOTH: All verified: {'YES' if overall_ok else 'NO'}")
        print("=" * 70)

    print()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
