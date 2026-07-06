#!/usr/bin/env python3
"""F9P Configurator v2 - MT 1005/1019/1020 有効化 + NMEA/UBX無効化 + 事後検証"""
import logging, time
from typing import Optional
import serial
from pyubx2 import UBXMessage, UBXReader, UBX_PROTOCOL

LAYER_ALL = 7  # RAM + BBR + FLASH

_RTCM3_ENABLE = [
    'CFG-MSGOUT-RTCM_3X_TYPE1005_UART1',  # ★ Station XYZ (MANDATORY)
    'CFG-MSGOUT-RTCM_3X_TYPE1074_UART1',  # GPS MSM4
    'CFG-MSGOUT-RTCM_3X_TYPE1084_UART1',  # GLO MSM4
    'CFG-MSGOUT-RTCM_3X_TYPE1094_UART1',  # GAL MSM4
    'CFG-MSGOUT-RTCM_3X_TYPE1124_UART1',  # BDS MSM4
    'CFG-MSGOUT-RTCM_3X_TYPE1019_UART1',  # ★ GPS Ephemeris
    'CFG-MSGOUT-RTCM_3X_TYPE1020_UART1',  # ★ GLO Ephemeris
    'CFG-MSGOUT-RTCM_3X_TYPE1042_UART1',  # BDS Ephemeris
    'CFG-MSGOUT-RTCM_3X_TYPE1230_UART1',  # GLO Bias
]

_RTCM3_DISABLE = [
    'CFG-MSGOUT-RTCM_3X_TYPE4072_0_UART1',
    'CFG-MSGOUT-RTCM_3X_TYPE4072_1_UART1',
]

_NMEA_DISABLE = [
    'CFG-MSGOUT-NMEA_ID_GGA_UART1', 'CFG-MSGOUT-NMEA_ID_GLL_UART1',
    'CFG-MSGOUT-NMEA_ID_GSA_UART1', 'CFG-MSGOUT-NMEA_ID_GSV_UART1',
    'CFG-MSGOUT-NMEA_ID_RMC_UART1', 'CFG-MSGOUT-NMEA_ID_VTG_UART1',
    'CFG-MSGOUT-NMEA_ID_ZDA_UART1',
]

_UBX_DISABLE = [
    'CFG-MSGOUT-UBX_NAV_STATUS_UART1', 'CFG-MSGOUT-UBX_NAV_DOP_UART1',
    'CFG-MSGOUT-UBX_NAV_SAT_UART1', 'CFG-MSGOUT-UBX_NAV_SIG_UART1',
]

_ALL_VERIFY = [
    'CFG-MSGOUT-RTCM_3X_TYPE1005_UART1', 'CFG-MSGOUT-RTCM_3X_TYPE1019_UART1',
    'CFG-MSGOUT-RTCM_3X_TYPE1020_UART1', 'CFG-MSGOUT-RTCM_3X_TYPE1042_UART1',
    'CFG-MSGOUT-RTCM_3X_TYPE1074_UART1', 'CFG-MSGOUT-RTCM_3X_TYPE1084_UART1',
    'CFG-MSGOUT-RTCM_3X_TYPE1094_UART1', 'CFG-MSGOUT-RTCM_3X_TYPE1124_UART1',
    'CFG-MSGOUT-RTCM_3X_TYPE1230_UART1',
    'CFG-MSGOUT-RTCM_3X_TYPE4072_0_UART1', 'CFG-MSGOUT-RTCM_3X_TYPE4072_1_UART1',
]

_NAMES = {
    '1005':'Station XYZ','1019':'GPS Eph','1020':'GLO Eph','1042':'BDS Eph',
    '1074':'GPS MSM4','1084':'GLO MSM4','1094':'GAL MSM4','1124':'BDS MSM4',
    '1230':'GLO Bias','4072_0':'ublox Prop0','4072_1':'ublox Prop1',
}

class F9pConfiguratorV2:
    def __init__(self, serial_port, baudrate=38400, logger=None):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.log = logger or logging.getLogger("F9pV2")
        self._ser = None

    def _open(self):
        self._ser = serial.Serial(self.serial_port, self.baudrate, timeout=1.0)
        time.sleep(0.3)
        self._ser.reset_input_buffer()

    def _close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
            self._ser = None

    def _send(self, msg):
        self._ser.write(msg)
        self._ser.flush()

    def _read_ubx(self, cls, mid, timeout=3.0):
        ubr = UBXReader(self._ser, protfilter=UBX_PROTOCOL)
        dl = time.time() + timeout
        while time.time() < dl:
            try:
                raw, parsed = ubr.read()
                if parsed and parsed.msg_cls == cls and parsed.msg_id == mid:
                    return raw
            except Exception:
                time.sleep(0.05)
        return None

    def step1_tmode3(self, lat, lon, alt, save=True):
        self._open()
        try:
            cfg = [
                ('CFG-TMODE-MODE', 2), ('CFG-TMODE-POS_TYPE', 0),
                ('CFG-TMODE-LAT', int(lat*1e7)), ('CFG-TMODE-LON', int(lon*1e7)),
                ('CFG-TMODE-HEIGHT', int(alt*100)),
            ]
            layers = LAYER_ALL if save else 1
            self._send(UBXMessage.config_set(layers, 0, cfg).serialize())
            self.log.info(f"STEP1 OK: TMODE3 FIXED {lat:.7f},{lon:.7f},{alt:.1f}")
            if save: time.sleep(0.5)
            return True
        except Exception as e:
            self.log.error(f"STEP1 FAIL: {e}")
            return False
        finally:
            self._close()

    def step2_messages(self, save=True):
        self._open()
        try:
            layers = LAYER_ALL if save else 1
            for label, keys in [("RTCM3 +ON", _RTCM3_ENABLE),
                                ("RTCM3 4072 -OFF", _RTCM3_DISABLE),
                                ("NMEA -OFF", _NMEA_DISABLE),
                                ("UBX -OFF", _UBX_DISABLE)]:
                cfg = [(k, 1 if '+ON' in label else 0) for k in keys]
                self._send(UBXMessage.config_set(layers, 0, cfg).serialize())
                self.log.info(f"STEP2: {label} ({len(cfg)} keys)")
                time.sleep(0.3)
            if save: time.sleep(1.0)
            return True
        except Exception as e:
            self.log.error(f"STEP2 FAIL: {e}")
            return False
        finally:
            self._close()

    def step3_verify(self):
        """全RTCM MSGOUTキーをポーリングして実際のON/OFF状態を確認

        MT 4072 系は意図的に無効化(0)しているので、0 なら ✅ と表示する。
        必須キー(1005, 1074)が 0 の場合は fatal 扱い。
        """
        # 各キーの期待値を事前に決める (1=ON期待, 0=OFF期待)
        expected = {}
        for k in _RTCM3_ENABLE:
            expected[k] = 1
        for k in _RTCM3_DISABLE:
            expected[k] = 0
        # リスト外のキーは「don't care」→ None

        self._open()
        result = {'verified': {}, 'all_ok': True, 'summary': []}
        try:
            self._send(UBXMessage.config_poll(0, 0, _ALL_VERIFY).serialize())
            raw = self._read_ubx(0x06, 0x8B, timeout=3.0)
            if raw and len(raw) >= 10:
                payload = raw[6:-2]
                pos = 4
                while pos + 4 <= len(payload):
                    kid = int.from_bytes(payload[pos:pos+4], 'little')
                    pos += 4
                    # key の上位 3bit から値サイズを取得 (U1=1, U2=2, U4=4, U8=8)
                    size_enc = (kid >> 28) & 0x07
                    val_size = {0x1: 1, 0x2: 1, 0x3: 2, 0x4: 4, 0x5: 8}.get(size_enc, 1)
                    if pos + val_size > len(payload):
                        break
                    val = int.from_bytes(payload[pos:pos+val_size], 'little')
                    pos += val_size
                    for k in _ALL_VERIFY:
                        try:
                            if UBXMessage.cfgkey_from_string(k) == kid:
                                tag = k.replace('CFG-MSGOUT-RTCM_3X_TYPE','').replace('_UART1','')
                                desc = _NAMES.get(tag, tag)
                                result['verified'][tag] = val
                                exp = expected.get(k)  # None → don't care
                                if exp is not None:
                                    ok = (val == exp)
                                    # 必須キーが期待値と違う → fatal
                                    if not ok and tag in ('1005', '1074'):
                                        result['all_ok'] = False
                                        mark = f'❌*** expected={exp}'
                                    elif not ok:
                                        mark = f'⚠️  expected={exp}'
                                    else:
                                        mark = '✅'
                                else:
                                    ok = True  # don't care
                                    mark = '✅' if val == 1 else '❌'
                                result['summary'].append(
                                    f"  {tag:8s} {desc:<20s} = {val}  {mark}")
                                break
                        except Exception:
                            continue
            else:
                self.log.warning("STEP3: No CFG-VALGET response")
                result['all_ok'] = False
        except Exception as e:
            self.log.error(f"STEP3 FAIL: {e}")
            result['all_ok'] = False
        finally:
            self._close()
        return result

    def configure(self, lat, lon, alt, save=True):
        r = {'step1': False, 'step2': False, 'step3': {}, 'all_ok': False}
        self.log.info("="*55)
        self.log.info("F9P V2 Configuration (Standard RTCM + Verification)")
        self.log.info("="*55)
        r['step1'] = self.step1_tmode3(lat, lon, alt, save)
        if r['step1']:
            r['step2'] = self.step2_messages(save)
        else:
            self.log.error("Aborting after STEP1 failure")
        r['step3'] = self.step3_verify()
        r['all_ok'] = r['step1'] and r['step2'] and r['step3'].get('all_ok', False)
        self.log.info("--- RTCM MSGOUT Verification ---")
        for line in r['step3'].get('summary', []):
            self.log.info(line)
        self.log.info(f"Overall: {'ALL OK' if r['all_ok'] else 'ISSUES FOUND'} " + "="*15)
        return r
