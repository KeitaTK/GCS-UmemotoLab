#!/usr/bin/env python3
"""f9p_verify_config.py - F9P Configuration Verification Tool

CFG-VALGET polling for base station and rover F9P settings.
Usage:
  python rtk_tools/f9p_verify_config.py --role base --port /dev/tty.usbmodem114301
  python rtk_tools/f9p_verify_config.py --role rover --port /dev/ttyAMA4
  python rtk_tools/f9p_verify_config.py --role rover --port /dev/ttyAMA4 --json
"""

import argparse, json, logging, sys, time
from typing import Any, Dict, List, Optional, Tuple
import serial
from pyubx2 import UBXMessage, UBXReader, UBX_PROTOCOL

LAYER_RAM = 1; LAYER_BBR = 2; LAYER_FLASH = 4
LAYER_ALL = LAYER_RAM | LAYER_BBR | LAYER_FLASH
_KEY_TMODE_MODE       = 0x20030001
_KEY_TMODE_POS_TYPE   = 0x20030002
_KEY_UART1_BAUDRATE   = 0x40520001
_KEY_UART1OUTPROT_UBX = 0x40520005
_KEY_UART2_BAUDRATE   = 0x40590001
_KEY_UART2INPROT_RTCM3X = 0x40590003
_KEY_UART2OUTPROT_UBX   = 0x40590005
_U4_KEYS = {_KEY_UART1_BAUDRATE, _KEY_UART2_BAUDRATE}
_RTCM_KEYS = [
    "CFG-MSGOUT-RTCM_3X_TYPE1005_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1006_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1074_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1084_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1094_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1124_UART1",
    "CFG-MSGOUT-RTCM_3X_TYPE1230_UART1",
]
_RTCM_TYPES = [k.split("TYPE")[1].split("_")[0] for k in _RTCM_KEYS]
_MAX_RETRIES = 3; _TIMEOUT = 5.0
_MON_VER = bytes([0xB5,0x62,0x0A,0x04,0x00,0x00,0x0E,0x34])
_OK="\u2705"; _FAIL="\u274c"; _WARN="\u26a0\ufe0f"


class F9pVerifier:
    """F9P config verifier - CFG-VALGET polling"""

    def __init__(self, serial_port: str, baudrate: int = 115200,
                 logger: Optional[logging.Logger] = None):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.logger = logger or logging.getLogger("F9pVerifier")
        self._ser: Optional[serial.Serial] = None

    def _open_serial(self):
        self.logger.info(f"Opening {self.serial_port} @ {self.baudrate}")
        ser = serial.Serial(self.serial_port, self.baudrate, timeout=1.0)
        time.sleep(0.3); ser.reset_input_buffer(); return ser

    def _close_serial(self):
        if self._ser and self._ser.is_open: self._ser.close(); self._ser = None

    def _send_ubx(self, msg: bytes):
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port not open")
        self._ser.write(msg); self._ser.flush()

    def _read_ubx(self, cls: int, mid: int, timeout: float = 3.0) -> Optional[bytes]:
        if not self._ser or not self._ser.is_open: return None
        ubr = UBXReader(self._ser, protfilter=UBX_PROTOCOL)
        dl = time.time() + timeout
        while time.time() < dl:
            try:
                raw, p = ubr.read()
                if p and p.msg_cls == cls and p.msg_id == mid: return raw
            except Exception: time.sleep(0.05)
        return None

    def _device_alive(self) -> bool:
        if not self._ser or not self._ser.is_open: return False
        try:
            self._ser.reset_input_buffer(); self._send_ubx(_MON_VER)
            raw = self._read_ubx(0x0A, 0x04, 3.0)
            if raw and len(raw) >= 8:
                self.logger.info("Device alive OK"); return True
            self.logger.warning("Device alive: no response"); return False
        except Exception as e:
            self.logger.error(f"Alive check failed: {e}"); return False

    def _poll_config(self, keys, timeout=_TIMEOUT, max_retries=_MAX_RETRIES):
        for attempt in range(1, max_retries + 1):
            self.logger.debug(f"CFG-VALGET attempt {attempt}/{max_retries}")
            poll_msg = UBXMessage.config_poll(0, 0, list(keys))
            self._ser.reset_input_buffer()
            self._send_ubx(poll_msg.serialize())
            raw = self._read_ubx(0x06, 0x8B, timeout=timeout)
            if raw and len(raw) >= 10: return raw
            if attempt < max_retries: time.sleep(1.0)
        self.logger.warning(f"No CFG-VALGET after {max_retries} attempts")
        return None

    def _parse_valget(self, raw):
        payload = raw[6:-2]
        result = {}
        if len(payload) < 4: return result
        layer = payload[1]
        pos = 4
        while pos + 4 <= len(payload):
            key_id = int.from_bytes(payload[pos:pos+4], "little")
            pos += 4
            if key_id in _U4_KEYS:
                if pos + 4 <= len(payload):
                    value = int.from_bytes(payload[pos:pos+4], "little")
                    pos += 4
                    result[key_id] = (value, layer)
            else:
                if pos < len(payload):
                    value = payload[pos]; pos += 1
                    result[key_id] = (value, layer)
        return result

    @staticmethod
    def _fail_open(check):
        check["status"] = "fail"
        check["suggestion"] = "Serial port not open"
        return check

    # --------------- Base Station ---------------

    def verify_base(self):
        result = {"role":"base","port":self.serial_port,"device_alive":False,
                  "checks":{},"all_passed":False,"suggestions":[]}
        self._ser = self._open_serial()
        try:
            alive = self._device_alive()
            result["device_alive"] = alive
            if not alive:
                result["suggestions"].append(
                    "Check serial, baudrate, power. f9p_configurator.py STEP1-3.")
                return result
            result["checks"]["tmode3"] = self._check_tmode3()
            result["checks"]["rtcm3_output"] = self._check_rtcm3_output()
            result["checks"]["uart1_baudrate"] = self._check_uart1_baudrate()
            result["checks"]["flash_save"] = self._check_flash_save()
            cl = list(result["checks"].values())
            failed = [n for n,c in result["checks"].items() if c.get("status")=="fail"]
            result["all_passed"] = all(c.get("status") in ("ok","warn") for c in cl) and alive
            for n in failed:
                s = result["checks"][n].get("suggestion","")
                if s: result["suggestions"].append(f"[{n}] {s}")
        except Exception as e:
            self.logger.error(f"Base error: {e}")
            result["all_passed"] = False
            result["suggestions"].append(f"Error: {e}")
        finally: self._close_serial()
        return result
    def _check_tmode3(self):
        check = {"name":"TMODE3 Fixed Mode","expected":"MODE=2 (FIXED)",
                 "actual":None,"status":"fail","icon":_FAIL,"details":{},"suggestion":""}
        if not self._ser or not self._ser.is_open: return self._fail_open(check)
        raw = self._poll_config(["CFG-TMODE-MODE", "CFG-TMODE-POS_TYPE"])
        if raw is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="No response"
            check["suggestion"]="F9P not responding. Re-run f9p_configurator.py STEP1-3."
            return check
        p = self._parse_valget(raw)
        mode_val,_ = p.get(_KEY_TMODE_MODE,(None,None))
        pos_val,_ = p.get(_KEY_TMODE_POS_TYPE,(None,None))
        check["details"]={"CFG-TMODE-MODE":mode_val,"CFG-TMODE-POS_TYPE":pos_val}
        mn = {0:"DISABLED",1:"SURVEY_IN",2:"FIXED"}
        pn = {0:"LLA",1:"ECEF"}
        if mode_val == 2:
            check["status"]="ok"; check["icon"]=_OK
            check["actual"]=f"MODE={mode_val} ({mn.get(mode_val,'?')}), POS_TYPE={pos_val} ({pn.get(pos_val,'?')})"
        elif mode_val is None:
            check["status"]="warn"; check["icon"]=_WARN
            check["actual"]="Response but key not found"
            check["suggestion"]="CFG-VALGET parse error. Re-run f9p_configurator.py."
        else:
            check["status"]="fail"; check["icon"]=_FAIL
            check["actual"]=f"MODE={mode_val} ({mn.get(mode_val,'?')}) - expected 2"
            check["suggestion"]="Re-run f9p_configurator.py STEP1 (TMODE3 FIXED)."
        return check

    def _check_rtcm3_output(self):
        check = {"name":"RTCM3 Output Messages (UART1)",
                 "expected":"7 msgs enabled (1005/1006/1074/1084/1094/1124/1230)",
                 "actual":None,"status":"fail","icon":_FAIL,"details":{},"suggestion":""}
        if not self._ser or not self._ser.is_open: return self._fail_open(check)
        raw = self._poll_config(_RTCM_KEYS)
        if raw is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="No response"
            check["suggestion"]="Re-run f9p_configurator.py STEP2."
            return check
        payload = raw[6:-2]; pos = 4
        msg_statuses = {t: -1 for t in _RTCM_TYPES}
        types_list = _RTCM_TYPES
        idx = 0
        while pos + 5 <= len(payload) and idx < len(types_list):
            _ = int.from_bytes(payload[pos:pos+4],"little"); pos += 4
            val = payload[pos]; pos += 1
            msg_statuses[types_list[idx]] = val; idx += 1
        enabled = sum(1 for v in msg_statuses.values() if v == 1)
        disabled = [t for t,v in msg_statuses.items() if v == 0]
        missing = sum(1 for v in msg_statuses.values() if v == -1)
        check["details"] = {t: v for t,v in msg_statuses.items()}
        if enabled == len(_RTCM_KEYS):
            check["status"]="ok"; check["icon"]=_OK
            check["actual"]=f"{enabled}/{len(_RTCM_KEYS)} enabled"
        elif missing > 0:
            check["status"]="warn"; check["icon"]=_WARN
            check["actual"]=f"{enabled}/{len(_RTCM_KEYS)} enabled, {missing} missing"
            check["suggestion"]="RTCM keys missing in response. Re-run f9p_configurator.py STEP2."
        else:
            check["status"]="fail"; check["icon"]=_FAIL
            check["actual"]=f"{enabled}/{len(_RTCM_KEYS)} enabled (disabled: {','.join(disabled)})"
            check["suggestion"]=f"Un-enabled: {','.join(disabled)}. Re-run f9p_configurator.py STEP2."
        return check

    def _check_uart1_baudrate(self):
        expected = 115200
        check = {"name":"UART1 Baudrate","expected":str(expected),
                 "actual":None,"status":"fail","icon":_FAIL,"details":{},"suggestion":""}
        if not self._ser or not self._ser.is_open: return self._fail_open(check)
        raw = self._poll_config(["CFG-UART1-BAUDRATE"])
        if raw is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="No response"
            check["suggestion"]="CFG-VALGET no response."
            return check
        p = self._parse_valget(raw)
        baud,_ = p.get(_KEY_UART1_BAUDRATE,(None,None))
        check["details"]={"CFG-UART1-BAUDRATE":baud}
        if baud == expected:
            check["status"]="ok"; check["icon"]=_OK; check["actual"]=str(baud)
        elif baud is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="Key not in response"
        else:
            check["status"]="fail"; check["icon"]=_FAIL; check["actual"]=str(baud)
            check["suggestion"]=f"UART1 baud={baud}, expected {expected}."
        return check

    def _check_flash_save(self):
        check = {"name":"Flash Save (TMODE3)",
                 "expected":"TMODE-MODE=2 persisted",
                 "actual":None,"status":"warn","icon":_WARN,"details":{},"suggestion":""}
        if not self._ser or not self._ser.is_open: return self._fail_open(check)
        raw = self._poll_config(["CFG-TMODE-MODE"])
        if raw is None:
            check["actual"]="No response"
            check["suggestion"]="Flash state unverifiable. Re-run f9p_configurator.py with --save-to-flash."
            return check
        p = self._parse_valget(raw)
        mode_val, layer = p.get(_KEY_TMODE_MODE,(None,None))
        check["details"]={"CFG-TMODE-MODE":mode_val,"response_layer":layer}
        ln = {1:"RAM",2:"BBR",4:"Flash",7:"ALL"}
        if mode_val == 2:
            check["status"]="ok"; check["icon"]=_OK
            check["actual"]=f"MODE=2, layer={layer} ({ln.get(layer,'?')})"
        elif mode_val is None:
            check["actual"]="Key not in response"
            check["suggestion"]="No value in Flash. Re-run with --save-to-flash."
        else:
            check["status"]="fail"; check["icon"]=_FAIL
            check["actual"]=f"MODE={mode_val}, layer={layer}"
            check["suggestion"]="Flash value mismatch. Re-run f9p_configurator.py."
        return check
    # --------------- Rover ---------------

    def verify_rover(self):
        result = {"role":"rover","port":self.serial_port,"device_alive":False,
                  "checks":{},"all_passed":False,"suggestions":[]}
        self._ser = self._open_serial()
        try:
            alive = self._device_alive()
            result["device_alive"] = alive
            if not alive:
                result["suggestions"].append(
                    "Check serial, baudrate, power. f9p_rover_config.py --port <PORT>.")
                return result
            result["checks"]["uart2_rtcm3_input"] = self._check_uart2_rtcm3()
            result["checks"]["uart2_baudrate"] = self._check_uart2_baudrate()
            result["checks"]["uart2_ubx_output"] = self._check_uart2_ubx_out()
            result["checks"]["can_output"] = self._check_can_output()
            cl = list(result["checks"].values())
            failed = [n for n,c in result["checks"].items() if c.get("status")=="fail"]
            result["all_passed"] = all(c.get("status") in ("ok","warn") for c in cl) and alive
            for n in failed:
                s = result["checks"][n].get("suggestion","")
                if s: result["suggestions"].append(f"[{n}] {s}")
        except Exception as e:
            self.logger.error(f"Rover error: {e}")
            result["all_passed"] = False
            result["suggestions"].append(f"Error: {e}")
        finally: self._close_serial()
        return result

    def _check_uart2_rtcm3(self):
        check = {"name":"UART2 RTCM3 Input (CFG-UART2INPROT-RTCM3X)",
                 "expected":"1 (enabled)",
                 "actual":None,"status":"fail","icon":_FAIL,"details":{},"suggestion":""}
        if not self._ser or not self._ser.is_open: return self._fail_open(check)
        raw = self._poll_config(["CFG-UART2INPROT-RTCM3X"])
        if raw is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="No response"
            check["suggestion"]="Re-run f9p_rover_config.py --port <PORT>."
            return check
        p = self._parse_valget(raw)
        val,_ = p.get(_KEY_UART2INPROT_RTCM3X,(None,None))
        check["details"]={"CFG-UART2INPROT-RTCM3X":val}
        if val == 1:
            check["status"]="ok"; check["icon"]=_OK; check["actual"]=f"{val} (RTCM3 input enabled)"
        elif val is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="Key not in response"
            check["suggestion"]="CFG-UART2INPROT-RTCM3X missing. Re-run f9p_rover_config.py."
        else:
            check["status"]="fail"; check["icon"]=_FAIL
            check["actual"]=f"{val} (disabled - should be 1)"
            check["suggestion"]=f"CFG-UART2INPROT-RTCM3X={val}, expected=1. Re-run f9p_rover_config.py."
        return check

    def _check_uart2_baudrate(self):
        expected = 115200
        check = {"name":"UART2 Baudrate","expected":str(expected),
                 "actual":None,"status":"fail","icon":_FAIL,"details":{},"suggestion":""}
        if not self._ser or not self._ser.is_open: return self._fail_open(check)
        raw = self._poll_config(["CFG-UART2-BAUDRATE"])
        if raw is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="No response"
            return check
        p = self._parse_valget(raw)
        baud,_ = p.get(_KEY_UART2_BAUDRATE,(None,None))
        check["details"]={"CFG-UART2-BAUDRATE":baud}
        if baud == expected:
            check["status"]="ok"; check["icon"]=_OK; check["actual"]=str(baud)
        elif baud is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="Key not in response"
        else:
            check["status"]="fail"; check["icon"]=_FAIL; check["actual"]=str(baud)
            check["suggestion"]=f"UART2 baud={baud}, expected {expected}."
        return check

    def _check_uart2_ubx_out(self):
        check = {"name":"UART2 UBX Output (CFG-UART2OUTPROT-UBX)",
                 "expected":"0 (disabled)",
                 "actual":None,"status":"fail","icon":_FAIL,"details":{},"suggestion":""}
        if not self._ser or not self._ser.is_open: return self._fail_open(check)
        raw = self._poll_config(["CFG-UART2OUTPROT-UBX"])
        if raw is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="No response"
            check["suggestion"]="Re-run f9p_rover_config.py --port <PORT>."
            return check
        p = self._parse_valget(raw)
        val,_ = p.get(_KEY_UART2OUTPROT_UBX,(None,None))
        check["details"]={"CFG-UART2OUTPROT-UBX":val}
        if val == 0:
            check["status"]="ok"; check["icon"]=_OK; check["actual"]=f"{val} (UBX output disabled)"
        elif val is None:
            check["status"]="warn"; check["icon"]=_WARN; check["actual"]="Key not in response"
            check["suggestion"]="CFG-UART2OUTPROT-UBX missing. Re-run f9p_rover_config.py."
        else:
            check["status"]="fail"; check["icon"]=_FAIL
            check["actual"]=f"{val} (UBX output enabled - should be 0)"
            check["suggestion"]=f"CFG-UART2OUTPROT-UBX={val}, expected=0. Re-run f9p_rover_config.py."
        return check

    def _check_can_output(self):
        check = {"name":"CAN Output (UART1->AP_Periph->DroneCAN)",
                 "expected":"UART1OUTPROT-UBX=1",
                 "actual":None,"status":"warn","icon":_WARN,"details":{},"suggestion":""}
        if not self._ser or not self._ser.is_open: return self._fail_open(check)
        raw = self._poll_config(["CFG-UART1OUTPROT-UBX"])
        if raw is None:
            check["actual"]="No response"
            check["details"]["note"]="AP_Periph DroneCAN params require UAVCAN GUI Tool."
            check["suggestion"]="F9P UART1 setting unreadable. DroneCAN need separate tool."
            return check
        p = self._parse_valget(raw)
        val,_ = p.get(_KEY_UART1OUTPROT_UBX,(None,None))
        check["details"]={"CFG-UART1OUTPROT-UBX":val,
                          "note":"AP_Periph DroneCAN params (CAN_GNSS_FIX2_EN etc) need UAVCAN GUI Tool."}
        if val == 1:
            check["status"]="ok"; check["icon"]=_OK
            check["actual"]=f"UART1OUTPROT-UBX=1 (UBX->AP_Periph OK); DroneCAN params need separate check"
            check["suggestion"]="AP_Periph DroneCAN params (CAN_GNSS_FIX2_EN/RATE) verify via DroneCAN tools."
        elif val is None:
            check["actual"]="Key not in response"
            check["suggestion"]="CFG-UART1OUTPROT-UBX missing from response."
        else:
            check["status"]="fail"; check["icon"]=_FAIL
            check["actual"]=f"UART1OUTPROT-UBX={val} (UBX output disabled)"
            check["suggestion"]=f"CFG-UART1OUTPROT-UBX={val}, expected=1. Enable manually."
        return check


# ================================================================
#  Display helpers
# ================================================================

def _print_header(role, port):
    print()
    print("=" * 65)
    print(f"  F9P Config Verification - {role.upper()} STATION")
    print(f"  Port: {port}")
    print("=" * 65)
    print()

def _print_check(check):
    icon = check.get("icon", _WARN)
    name = check.get("name", "Unknown")
    status = check.get("status", "warn")
    actual = check.get("actual", "N/A")
    suggestion = check.get("suggestion", "")
    labels = {"ok": "OK", "fail": "FAIL", "warn": "WARN"}
    label = labels.get(status, "WARN")
    print(f"  {icon} [{label:4s}] {name}")
    print(f"          Expected : {check.get('expected', 'N/A')}")
    print(f"          Actual   : {actual}")
    if suggestion:
        print(f"          Fix      : {suggestion}")
    print()

def _print_suggestions(suggestions):
    if not suggestions:
        return
    print("-" * 65)
    print("  Fix Suggestions:")
    for i, s in enumerate(suggestions, 1):
        print(f"    {i}. {s}")
    print("-" * 65)

def _print_summary(all_passed, device_alive):
    print()
    print("=" * 65)
    if not device_alive:
        print("  Device alive          : NO  (check connection/baudrate)")
    passed_str = "YES" if all_passed else "NO"
    overall = _OK if all_passed else (_WARN if device_alive else _FAIL)
    print(f"  {overall} All checks passed    : {passed_str}")
    print("=" * 65)
    print()


# ================================================================
#  CLI Entry Point
# ================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="F9P Configuration Verification Tool",
        epilog="Examples:\n"
        "  python rtk_tools/f9p_verify_config.py --role base --port /dev/tty.usbmodem114301\n"
        "  python rtk_tools/f9p_verify_config.py --role rover --port /dev/ttyAMA4\n"
        "  python rtk_tools/f9p_verify_config.py --role rover --port /dev/ttyAMA4 --json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--role", required=True, choices=["base","rover","both"],
                        help="Target: base, rover, or both")
    parser.add_argument("--port", default=None,
                        help="Serial port (for single role)")
    parser.add_argument("--base-port", default="/dev/tty.usbmodem114301",
                        help="Base station port (--role both)")
    parser.add_argument("--rover-port", default="/dev/ttyAMA4",
                        help="Rover port (--role both)")
    parser.add_argument("--baud", type=int, default=115200,
                        help="Baudrate (default: 115200)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--log-level", default="WARNING",
                        choices=["DEBUG","INFO","WARNING","ERROR"],
                        help="Log level (default: WARNING)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("f9p_verify")

    results: Dict[str, Any] = {}
    exit_code = 0

    if args.role in ("base", "both"):
        port = args.port if args.role == "base" else args.base_port
        if not port:
            print("Error: --port required for --role base", file=sys.stderr)
            return 1
        v = F9pVerifier(serial_port=port, baudrate=args.baud, logger=logger)
        results["base"] = v.verify_base()
        if not results["base"].get("all_passed"):
            exit_code = 1

    if args.role in ("rover", "both"):
        port = args.port if args.role == "rover" else args.rover_port
        if not port:
            print("Error: --port required for --role rover", file=sys.stderr)
            return 1
        v = F9pVerifier(serial_port=port, baudrate=args.baud, logger=logger)
        results["rover"] = v.verify_rover()
        if not results["rover"].get("all_passed"):
            exit_code = 1

    if args.json:
        if args.role == "both":
            all_ok = (results.get("base",{}).get("all_passed",False) and
                      results.get("rover",{}).get("all_passed",False))
        else:
            all_ok = results.get(args.role,{}).get("all_passed",False)
        results["all_passed"] = all_ok
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for role_key, role_label in [("base","BASE"), ("rover","ROVER")]:
            if role_key not in results:
                continue
            r = results[role_key]
            _print_header(role_label, r["port"])
            if not r["device_alive"]:
                print(f"  {_FAIL} Device not responding - cannot verify")
                _print_suggestions(r.get("suggestions",[]))
                _print_summary(False, False)
            else:
                for check in r["checks"].values():
                    _print_check(check)
                _print_suggestions(r.get("suggestions",[]))
                _print_summary(r["all_passed"], r["device_alive"])

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
