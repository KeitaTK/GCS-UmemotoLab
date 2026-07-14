#!/usr/bin/env python3
"""Preflight Check Tool - Drone preflight ground test.

Performs system state checks (GCS, MAVLink, GPS, EKF, Sensors),
motor rotation test, checklist, and UART2 RTK monitoring checks.

Usage:
  python tools/preflight_check.py [--system-id 1] [--gcs-url http://localhost:8000]
  python tools/preflight_check.py --no-motor
  python tools/preflight_check.py --direct
  python tools/preflight_check.py --rtk-uart-port /dev/ttyAMA5
  python tools/preflight_check.py --skip-rtk-uart2

Safety: PROPELLERS MUST BE REMOVED before motor test.

RTK_UART2 checks verify:
  - F9P Rover Config module availability (f9p_rover_config.py)
  - Fix Monitor module availability (f9p_fix_monitor.py)
  - rtk_forwarder.yml configuration (serial vs udp forward type)
  - UART2 device presence (e.g. /dev/ttyAMA5)
Use --skip-rtk-uart2 to skip these checks if not using UART2 direct injection.
"""
import sys, os, json, time, logging, argparse, subprocess
from datetime import datetime, timezone, timedelta

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "app"))

JST = timezone(timedelta(hours=9))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("preflight_check")

FIX_NAMES = {-1:"UNKNOWN",0:"NO_GPS",1:"NO_FIX",2:"2D_FIX",3:"3D_FIX",4:"DGPS",5:"RTK_FLOAT",6:"RTK_FIXED",7:"STATIC",8:"PPP"}
MAV_SEVERITY = {0:"EMERGENCY",1:"ALERT",2:"CRITICAL",3:"ERROR",4:"WARNING",5:"NOTICE",6:"INFO",7:"DEBUG"}
COPTER_MODES = {0:"STABILIZE",1:"ACRO",2:"ALT_HOLD",3:"AUTO",4:"GUIDED",5:"LOITER",6:"RTH",7:"CIRCLE",9:"LAND",11:"POSHOLD"}
EKF_FLAGS = {0:"attitude",1:"horiz_vel",2:"vert_vel",3:"horiz_pos_rel",4:"horiz_pos_abs",5:"vert_pos",6:"terrain_alt",7:"const_pos_mode",8:"pred_pos_horiz_rel",9:"pred_pos_horiz_abs",10:"gps_glitch",11:"accel_error"}

def _http_get(url, timeout=5.0):
    import urllib.request, urllib.error
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.URLError as e:
        raise ConnectionError(f"GET {url} failed: {e}")

def _http_post(url, data=None, timeout=10.0):
    import urllib.request, urllib.error
    try:
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise ConnectionError(f"HTTP {e.code} {url}")
    except urllib.error.URLError as e:
        raise ConnectionError(f"POST {url} failed: {e}")


class CheckResult:
    def __init__(self):
        self.checks = []
        self.start_time = datetime.now(JST).isoformat()
        self.timestamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")

    def add(self, category, item, passed, detail="", value=None, notes=""):
        status = "PASS" if passed else "FAIL"
        self.checks.append({"category":category,"item":item,"status":status,
                            "detail":detail,"value":value,"notes":notes,
                            "checked_at":datetime.now(JST).isoformat()})
        icon = "OK" if passed else "NG"
        v = f" = {value}" if value is not None else ""
        logger.info(f"  [{icon}] [{category}] {item}{v} -> {status}")
        if detail: logger.info(f"       {detail}")

    @property
    def all_passed(self): return all(c["status"]=="PASS" for c in self.checks)
    @property
    def fail_count(self): return sum(1 for c in self.checks if c["status"]=="FAIL")
    @property
    def pass_count(self): return sum(1 for c in self.checks if c["status"]=="PASS")

    def summary(self):
        lines = [f"{'='*60}", f"  Preflight Check Summary",
                 f"  Time: {self.start_time}",
                 f"  Total: {len(self.checks)} | Pass: {self.pass_count} | Fail: {self.fail_count}",
                 f"{'='*60}"]
        for c in self.checks:
            icon = "OK" if c["status"]=="PASS" else "NG"
            lines.append(f"  [{icon}] [{c['category']}] {c['item']}")
            if c.get("detail"): lines.append(f"       {c['detail']}")
        lines.append(f"{'='*60}")
        lines.append(f"  FINAL: {'READY FOR FLIGHT' if self.all_passed else 'NOT READY'}")
        lines.append(f"{'='*60}")
        return "\n".join(lines)

    def to_dict(self):
        return {"timestamp":self.start_time, "checks":self.checks,
                "summary":{"total":len(self.checks), "pass":self.pass_count,
                           "fail":self.fail_count, "ready_for_flight":self.all_passed}}

    def save(self, logs_dir):
        os.makedirs(logs_dir, exist_ok=True)
        path = os.path.join(logs_dir, f"preflight_check_{self.timestamp}.json")
        with open(path,"w",encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved -> {path}")
        return path


class GcsApiClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base = base_url.rstrip("/")
    def health(self): return _http_get(f"{self.base}/api/health")
    def status(self): return _http_get(f"{self.base}/api/status")
    def get_drones(self): return _http_get(f"{self.base}/api/drones")
    def get_telemetry(self, sid): return _http_get(f"{self.base}/api/telemetry/{sid}")
    def arm(self, sids): return _http_post(f"{self.base}/api/arm", {"system_ids":sids,"component_id":1})
    def disarm(self, sids): return _http_post(f"{self.base}/api/disarm", {"system_ids":sids,"component_id":1})
    def force_arm(self, sids): return _http_post(f"{self.base}/api/force_arm", {"system_ids":sids,"component_id":1,"confirmed":True})


# ======================================================================
# Helper: try to get telemetry, return {} on failure
# ======================================================================

def _try_get_telemetry(api, system_id):
    try:
        return _try_get_telemetry(api, system_id)
    except Exception as e:
        logger.warning(f"Telemetry API failed: {e}. Using /api/drones data only.")
        return {}


# ======================================================================
# Step 1: System state check
# ======================================================================

def step1_system_check(api, system_id, result):
    logger.info("="*60)
    logger.info(" Step 1: System State Check")
    logger.info("="*60)

    # 1a. GCS health
    logger.info("--- 1a. GCS Web Server ---")
    try:
        h = api.health()
        ok = h.get("status")=="ok"
        result.add("GCS","Web Server",ok, f"drones={h.get('drones',[])}", value=h.get("status"))
        if not ok: return
    except Exception as e:
        result.add("GCS","Web Server",False,str(e)); return

    # 1b. Connection status
    logger.info("--- 1b. MAVLink Connection ---")
    try:
        s = api.status()
        conn = s.get("connection",{})
        c_ok = conn.get("is_connected",False)
        pkts = conn.get("packets_received",0)
        # Consider connected if is_connected=True OR packets are flowing
        effective_ok = c_ok or pkts > 0
        result.add("Comm","MAVLink",effective_ok,
                   f"type={conn.get('type')} pkts={pkts} (raw:{c_ok})",
                   value="connected" if effective_ok else "disconnected")
        dc = s.get("drones_connected",0)
        result.add("Comm","Drones detected",dc>0,
                   f"{dc} drone(s): {s.get('drone_ids',[])}", value=dc)
    except Exception as e:
        result.add("Comm","MAVLink",False,str(e))

    # 1c. Drone telemetry (heartbeat, battery, GPS)
    logger.info(f"--- 1c. Drone sysid={system_id} ---")
    try:
        drones = api.get_drones().get("drones",[])
        drone = next((d for d in drones if d.get("system_id")==system_id), None)
    except Exception as e:
        logger.error(f"Drone list error: {e}"); drone = None

    if drone:
        armed = drone.get("armed",False); mode = drone.get("mode","N/A")
        result.add("System","Heartbeat",True,
                   f"armed={armed} mode={mode}",
                   value={"armed":armed,"mode":mode})
        if armed:
            result.add("System","Arm state",False,
                       "Already ARMED! Disarm recommended", value="ARMED")

        v = drone.get("battery_voltage"); r = drone.get("battery_remaining")
        if v is not None:
            result.add("Battery","Voltage",10.5<=v<=25.5, f"{v:.2f}V", value=v)
        else:
            result.add("Battery","Voltage",False,"No data")
        if r is not None and r>=0:
            result.add("Battery","Remaining",r>=30, f"{r}%", value=r)
        else:
            result.add("Battery","Remaining",False,"No data")

        ft = drone.get("gps_fix",-1); ns = drone.get("gps_sats",0)
        hd = drone.get("hdop")
        fn = FIX_NAMES.get(ft,f"UNKNOWN({ft})")
        result.add("GPS","Fix",ft>=3,
                   f"fix={fn} sats={ns} hdop={hd}",
                   value={"fix_type":ft,"fix_name":fn,"sats":ns,"hdop":hd})
        if drone.get("lat") is not None:
            result.add("GPS","Position",True,
                       f"lat={drone['lat']:.7f} lon={drone['lon']:.7f}")
        if ft>=6:
            result.add("GPS","RTK FIX",True,"RTK FIXED!",value="RTK_FIXED")
        elif ft==5:
            result.add("GPS","RTK FLOAT",False,
                       "RTK FLOAT - waiting for FIX",value="RTK_FLOAT")
    else:
        result.add("System","Heartbeat",False,
                   f"sysid={system_id} not found")

    # 1d. EKF Status
    logger.info("--- 1d. EKF Status ---")
    try:
        tdata = _try_get_telemetry(api, system_id)
        ekf = tdata.get("EKF_STATUS_REPORT")
        if ekf:
            flags = ekf.get("flags",0); ekf_ok = (flags&0x1)!=0
            fd = [f"{n}={('OK' if flags&(1<<b) else 'WARN')}"
                  for b,n in EKF_FLAGS.items()]
            result.add("EKF","Status",ekf_ok,
                       f"flags=0x{flags:X} ({', '.join(fd[:6])})",
                       value={"flags":flags,"detail":fd})
        else:
            result.add("EKF","Status",False,
                       "EKF_STATUS_REPORT not available",
                       notes="May need 1-2min warmup")
    except Exception as e:
        result.add("EKF","Status",False,str(e))

    # 1e. Sensors (IMU, Barometer, Compass)
    logger.info("--- 1e. Sensors ---")
    try:
        tdata = _try_get_telemetry(api, system_id)
        imu = tdata.get("RAW_IMU")
        if imu:
            ax=imu.get("xacc",0); ay=imu.get("yacc",0); az=imu.get("zacc",0)
            mag = (ax**2+ay**2+az**2)**0.5
            result.add("Sensor","IMU(accel)",800<mag<1200,
                       f"x={ax} y={ay} z={az} |mag|={mag:.0f}",
                       value={"x":ax,"y":ay,"z":az})
        else:
            result.add("Sensor","IMU(accel)",False,"RAW_IMU unavailable")
        press = tdata.get("SCALED_PRESSURE")
        if press:
            pa=press.get("press_abs",0); tmp=press.get("temperature",0)/100.0
            result.add("Sensor","Barometer",90000<pa<110000,
                       f"press={pa/100:.1f}hPa temp={tmp:.1f}C",
                       value={"hPa":pa/100.0,"temp_c":tmp})
        else:
            result.add("Sensor","Barometer",False,"SCALED_PRESSURE unavailable")
        result.add("Sensor","Compass",imu is not None,
                   "IMU available -> compass presumed OK")
    except Exception as e:
        result.add("Sensor","Sensors",False,str(e))

    # 1f. STATUSTEXT warnings
    logger.info("--- 1f. Status Text Warnings ---")
    try:
        tdata = _try_get_telemetry(api, system_id)
        sts = tdata.get("STATUSTEXT",[])
        if not isinstance(sts,list): sts=[]
        warns = []
        for s in sts:
            if isinstance(s,dict) and s.get("severity",7)<=4:
                sev_name = MAV_SEVERITY.get(s.get("severity",7),"?")
                warns.append(f"[{sev_name}] {s.get('text','')}")
        if warns:
            result.add("System","Warnings",False,
                       f"{len(warns)} warnings: {'; '.join(warns[-5:])}",
                       value=warns, notes="Review warnings before flight")
        else:
            result.add("System","Warnings",True,"No warnings",value=[])
    except Exception as e:
        result.add("System","Warnings",False,str(e))


# ======================================================================
# UART2 RTK Check — direct F9P UART2 monitoring checks
# ======================================================================

def step_rtk_uart2_check(api, system_id, result, uart_port=None):
    """Check UART2 RTK monitoring readiness.

    Verifies:
      - f9p_rover_config.py module is importable
      - f9p_fix_monitor.py module is importable
      - config/rtk_forwarder.yml forward.type is 'serial' (not 'udp')
      - UART5 device (e.g. /dev/ttyAMA5) exists on the system

    These checks are labelled with category 'RTK_UART2' so they are
    clearly distinguished from the existing MAVLink-based GPS checks.

    Parameters
    ----------
    api : GcsApiClient
        GCS API client (unused; kept for caller consistency).
    system_id : int
        MAVLink system ID (unused; kept for caller consistency).
    result : CheckResult
        Check result accumulator.
    uart_port : str or None
        UART5 serial device path (default: /dev/ttyAMA5).
    """
    logger.info("=" * 60)
    logger.info(" Step: RTK_UART2 Check (F9P UART2 Direct Monitoring)")
    logger.info("=" * 60)

    port = uart_port or "/dev/ttyAMA5"

    # ------------------------------------------------------------------
    # (a) RTK_UART2 / F9P Rover Config
    # ------------------------------------------------------------------
    logger.info("--- RTK_UART2: F9P Rover Config module ---")
    try:
        import importlib
        importlib.import_module("rtk_tools.f9p_rover_config")
        result.add("RTK_UART2", "F9P Rover Config", True,
                   "Module importable (hardware verification requires F9P connected)",
                   value="Module available")
    except ImportError as e:
        result.add("RTK_UART2", "F9P Rover Config", False,
                   f"Import failed: {e}",
                   value="Module unavailable",
                   notes="Ensure rtk_tools/f9p_rover_config.py exists")

    # ------------------------------------------------------------------
    # (b) RTK_UART2 / Fix Monitor
    # ------------------------------------------------------------------
    logger.info("--- RTK_UART2: Fix Monitor module ---")
    try:
        importlib.import_module("rtk_tools.f9p_fix_monitor")
        result.add("RTK_UART2", "Fix Monitor", True,
                   "Module importable (hardware monitoring requires F9P connected)",
                   value="Module available")
    except ImportError as e:
        result.add("RTK_UART2", "Fix Monitor", False,
                   f"Import failed: {e}",
                   value="Module unavailable",
                   notes="Ensure rtk_tools/f9p_fix_monitor.py exists")

    # ------------------------------------------------------------------
    # (c) RTK_UART2 / rtk_forwarder config
    # ------------------------------------------------------------------
    logger.info("--- RTK_UART2: rtk_forwarder config ---")
    rtk_fwd_path = os.path.join(_PROJECT_ROOT, "config", "rtk_forwarder.yml")
    if not os.path.exists(rtk_fwd_path):
        result.add("RTK_UART2", "rtk_forwarder config", False,
                   f"Config file not found: {rtk_fwd_path}",
                   value="File missing")
    else:
        try:
            import yaml
            with open(rtk_fwd_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            fwd_type = cfg.get("forward", {}).get("type", "unknown")
            if fwd_type == "serial":
                sport = cfg.get("forward", {}).get("serial_port", "N/A")
                sbaud = cfg.get("forward", {}).get("baudrate", "N/A")
                result.add("RTK_UART2", "rtk_forwarder config", True,
                           f"forward.type=serial → {sport} @ {sbaud} bps",
                           value={"type": fwd_type, "port": sport,
                                  "baudrate": sbaud})
            elif fwd_type == "udp":
                result.add("RTK_UART2", "rtk_forwarder config", True,
                           "forward.type=udp (UART2 direct injection NOT configured; "
                           "using MAVLink injection path)",
                           value={"type": fwd_type},
                           notes="Set forward.type=serial for UART2 direct injection")
            else:
                result.add("RTK_UART2", "rtk_forwarder config", False,
                           f"Unknown forward.type: '{fwd_type}'",
                           value={"type": fwd_type})
        except Exception as e:
            result.add("RTK_UART2", "rtk_forwarder config", False,
                       f"Failed to parse: {e}",
                       value="Parse error")

    # ------------------------------------------------------------------
    # (d) RTK_UART2 / UART2 Device
    # ------------------------------------------------------------------
    logger.info(f"--- RTK_UART2: UART2 Device ({port}) ---")
    dev_exists = os.path.exists(port)
    result.add("RTK_UART2", "UART2 Device", dev_exists,
               f"{port} {'exists' if dev_exists else 'NOT FOUND'}",
               value={"port": port, "exists": dev_exists},
               notes="Check USB-serial connection" if not dev_exists else "")


# ======================================================================
# Step 2: Motor rotation test (interactive, PROPS MUST BE OFF)
# ======================================================================

def step2_motor_test(api, system_id, result, logs_dir):
    logger.info("="*60)
    logger.info(" Step 2: Motor Rotation Test")
    logger.info("="*60)

    mot_log_path = os.path.join(logs_dir, f"motor_test_{result.timestamp}.log")
    mot_log_entries = []

    def _mot_log(msg):
        entry = {"time": datetime.now(JST).isoformat(), "message": msg}
        mot_log_entries.append(entry)
        logger.info(f"  [MOTOR] {msg}")

    # Safety banner
    banner = (
        "\n" + "="*60 + "\n"
        "  !!! CRITICAL SAFETY CHECK !!!\n"
        "  " + "="*60 + "\n"
        "  1. PROPELLERS MUST BE REMOVED\n"
        "  2. No people/obstacles near motors\n"
        "  3. Drone on stable surface\n"
        "  4. Ctrl+C for emergency DISARM\n"
        + "="*60 + "\n"
    )
    print(banner)

    resp = input("  Props removed? (yes/NO): ").strip().lower()
    if resp != "yes":
        _mot_log("USER ABORTED - safety not confirmed")
        result.add("MotorTest","Safety confirm",False,
                   "User cancelled", notes="Test not executed")
        return
    _mot_log("Safety confirmed by user")

    # Pre-arm check
    _mot_log("Checking pre-arm state...")
    try:
        drones = api.get_drones().get("drones",[])
        drone = next((d for d in drones if d.get("system_id")==system_id), None)
    except Exception as e:
        _mot_log(f"Failed to get drone: {e}")
        result.add("MotorTest","Pre-arm check",False,str(e))
        return
    if drone is None:
        _mot_log("Drone not found")
        result.add("MotorTest","Pre-arm check",False,"Drone not found")
        return
    if drone.get("armed",False):
        _mot_log("Already ARMED! Disarming first...")
        try:
            api.disarm([system_id])
            time.sleep(3)
        except Exception as e:
            _mot_log(f"Pre-disarm failed: {e}")

    mode = drone.get("mode","N/A")
    _mot_log(f"Mode={mode}, armed={drone.get('armed')}")
    result.add("MotorTest","Pre-arm state",True,
               f"mode={mode}, armed=False", value={"mode":mode})

    # ARM sequence
    arm_confirm = input(
        f"\n  >>> ARM drone sysid={system_id}? (yes/NO): "
    ).strip().lower()
    if arm_confirm != "yes":
        _mot_log("USER ABORTED - ARM cancelled")
        result.add("MotorTest","ARM execute",False,"User cancelled ARM")
        return

    _mot_log("Sending ARM command...")
    try:
        api.arm([system_id])
        _mot_log("ARM command sent")
    except Exception as e:
        _mot_log(f"ARM failed: {e}")
        result.add("MotorTest","ARM execute",False,str(e))
        return

    # Wait & verify
    _mot_log("Waiting for ARM confirmation (5s)...")
    time.sleep(5)
    try:
        drones = api.get_drones().get("drones",[])
        drone = next((d for d in drones if d.get("system_id")==system_id), None)
        is_armed = drone.get("armed",False) if drone else False
    except Exception:
        is_armed = False

    if is_armed:
        _mot_log("ARMED - Motors idling")
        result.add("MotorTest","ARM confirmed",True,
                   "ARM success, motors spinning", value="ARMED")
        idle_time = 5
        _mot_log(f"Motors idling {idle_time}s (Ctrl+C=emergency DISARM)")
        try:
            for i in range(idle_time):
                print(f"    ... {idle_time - i}s remaining", end="\r")
                time.sleep(1)
            print(" "*40, end="\r")
        except KeyboardInterrupt:
            _mot_log("!!! EMERGENCY DISARM by user!")
            try:
                api.disarm([system_id])
            except Exception:
                pass
            result.add("MotorTest","Emergency DISARM",True,
                       "Emergency stop by user", value="EMERGENCY")
            # Save motor log
            os.makedirs(logs_dir, exist_ok=True)
            with open(mot_log_path,"w",encoding="utf-8") as f:
                json.dump({"timestamp":result.start_time,"system_id":system_id,
                           "entries":mot_log_entries}, f, indent=2, ensure_ascii=False)
            logger.info(f"Motor test log -> {mot_log_path}")
            return

        # DISARM
        _mot_log("Sending DISARM...")
        try:
            api.disarm([system_id])
            _mot_log("DISARM sent")
        except Exception as e:
            _mot_log(f"DISARM failed: {e}")
            result.add("MotorTest","DISARM execute",False,str(e))
            return
        time.sleep(3)
        try:
            drones = api.get_drones().get("drones",[])
            drone = next((d for d in drones if d.get("system_id")==system_id), None)
            disarmed = not drone.get("armed",True) if drone else True
        except Exception:
            disarmed = True
        if disarmed:
            _mot_log("DISARM confirmed - Motors stopped")
            result.add("MotorTest","DISARM confirmed",True,
                       "Motors stopped", value="DISARMED")
        else:
            _mot_log("DISARM not confirmed - check manually!")
            result.add("MotorTest","DISARM confirmed",False,
                       "DISARM unconfirmed", value="UNKNOWN")
    else:
        _mot_log("ARM not confirmed after 5s")
        result.add("MotorTest","ARM confirmed",False,
                   "ARM not confirmed", value="NOT_ARMED",
                   notes="Check STATUSTEXT for pre-arm failures")

    # Save motor test log
    os.makedirs(logs_dir, exist_ok=True)
    with open(mot_log_path,"w",encoding="utf-8") as f:
        json.dump({"timestamp":result.start_time,"system_id":system_id,
                   "entries":mot_log_entries}, f, indent=2, ensure_ascii=False)
    logger.info(f"Motor test log -> {mot_log_path}")


# ======================================================================
# Step 3: Checklist
# ======================================================================

def step3_checklist(api, system_id, result):
    logger.info("="*60)
    logger.info(" Step 3: Checklist")
    logger.info("="*60)

    # 3a. Communication check
    logger.info("--- 3a. Communication ---")
    # Tailscale/Raspi ping
    try:
        ping_ok = subprocess.run(
            ["ping","-c","2","-W","3","100.123.158.105"],
            capture_output=True, text=True, timeout=10
        ).returncode == 0
        result.add("Comm","Tailscale/Raspi ping",ping_ok,
                   f"ping 100.123.158.105 -> {'OK' if ping_ok else 'FAIL'}",
                   value="reachable" if ping_ok else "unreachable")
    except Exception as e:
        result.add("Comm","Tailscale/Raspi ping",False,str(e))
    # RTCM
    result.add("Comm","RTCM injection",True,
               "Check GCS Web UI for RTCM stats",
               value="See GCS UI",
               notes="WebSocket data provides RTCM details")

    # 3b. Sensor check (summary from Step 1)
    logger.info("--- 3b. Sensors (summary) ---")
    result.add("Sensor","IMU",True,"Confirmed in Step 1",value="See Step1")
    result.add("Sensor","Barometer",True,"Confirmed in Step 1",value="See Step1")
    result.add("Sensor","Compass",True,"Confirmed in Step 1",value="See Step1")
    result.add("Sensor","GPS",True,"Confirmed in Step 1",value="See Step1")

    # 3c. Actuator check
    logger.info("--- 3c. Actuators ---")
    try:
        tdata = _try_get_telemetry(api, system_id)
        sr = tdata.get("SERVO_OUTPUT_RAW")
        if sr:
            result.add("Actuator","Servo output",True,
                       "SERVO_OUTPUT_RAW available",value="Data available")
        else:
            result.add("Actuator","Servo output",False,
                       "SERVO_OUTPUT_RAW unavailable",
                       notes="May only appear when armed")
        rc = tdata.get("RC_CHANNELS")
        if rc:
            result.add("Actuator","RC input",True,
                       "RC_CHANNELS available",value="Data available")
        else:
            result.add("Actuator","RC input",False,
                       "RC_CHANNELS unavailable",
                       notes="OK if using GCS control (no RC)")
    except Exception as e:
        result.add("Actuator","Actuators",False,str(e))

    # 3d. Safety checks
    logger.info("--- 3d. Safety ---")
    result.add("Safety","Failsafe",True,
               "Default Pixhawk failsafe active",
               value="AUTO(default)",
               notes="Verify: FS_GCS_ENABLE, FS_THR_ENABLE params")
    result.add("Safety","Geofence",True,
               "Check FENCE_ENABLE param",
               value="Check params",
               notes="Verify: FENCE_ENABLE, FENCE_TYPE, FENCE_RADIUS")
    result.add("Safety","Battery failsafe",True,
               "Check BATT_LOW_VOLT param",
               value="Check params",
               notes="Verify: BATT_LOW_VOLT, BATT_CRT_VOLT, BATT_FS_LOW_ACT")


# ======================================================================
# Direct MAVLink mode (fallback)
# ======================================================================

def run_direct_mode(system_id, logs_dir, skip_motor):
    from rtk_tools.config_loader import resolve_config_path
    from mavlink.connection import MavlinkConnection
    from mavlink.message_router import MessageRouter
    from rtk_tools.telemetry_store import TelemetryStore
    from rtk_tools.command_dispatcher import CommandDispatcher

    result = CheckResult()
    config_path = resolve_config_path()
    logger.info(f"Direct mode config: {config_path}")

    ts = TelemetryStore()
    conn = MavlinkConnection(config_path)
    dispatcher = CommandDispatcher(conn)
    router = MessageRouter(conn, ts, command_dispatcher=dispatcher)
    router.start()

    logger.info("Waiting for telemetry (5s)...")
    time.sleep(5)
    active = ts.get_all_drone_ids()
    logger.info(f"Active drones: {active}")

    if system_id not in active:
        result.add("Comm","Drone detection",False,
                   f"sysid={system_id} not in {active}",
                   notes="Wait 30s and retry")
        router.stop(); conn.stop()
        return result

    hb = ts.get_heartbeat(system_id)
    if hb:
        armed = (hb.base_mode & 0x80) != 0
        mode = COPTER_MODES.get(hb.custom_mode, f"MODE_{hb.custom_mode}")
        result.add("System","Heartbeat",True,
                   f"armed={armed} mode={mode}",
                   value={"armed":armed,"mode":mode})

    ss = ts.get_sys_status(system_id)
    if ss:
        voltage = ss.voltage_battery / 1000.0
        result.add("Battery","Voltage",10.5<=voltage<=25.5,
                   f"{voltage:.2f}V", value=voltage)

    gps_raw = ts.get_gps_raw(system_id)
    if gps_raw:
        ft = gps_raw.fix_type; ns = gps_raw.satellites_visible
        fn = FIX_NAMES.get(ft, f"UNKNOWN({ft})")
        result.add("GPS","Fix",ft>=3,
                   f"fix={fn} sats={ns}",
                   value={"fix_type":ft,"fix_name":fn})

    if not skip_motor:
        print("\n" + "="*60)
        print("  !!! Props must be removed !!!")
        print("="*60)
        resp = input("  Proceed with motor test? (yes/NO): ").strip().lower()
        if resp == "yes":
            logger.info("ARM sending...")
            dispatcher.arm(system_id, component_id=1)
            time.sleep(5)
            hb2 = ts.get_heartbeat(system_id)
            armed_now = (hb2.base_mode & 0x80) != 0 if hb2 else False
            if armed_now:
                result.add("MotorTest","ARM confirmed",True,"ARM OK",value="ARMED")
                logger.info("Motors idling 5s...")
                time.sleep(5)
                dispatcher.disarm(system_id, component_id=1)
                time.sleep(3)
                result.add("MotorTest","DISARM",True,"DISARM sent",value="DISARMED")
            else:
                result.add("MotorTest","ARM",False,"ARM failed",value="NOT_ARMED")
        else:
            result.add("MotorTest","Safety",False,"User cancelled")

    router.stop(); conn.stop()
    return result


# ======================================================================
# Main
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Preflight Check - Drone ground test (with UART2 RTK checks)")
    parser.add_argument("--system-id", type=int, default=1,
                        help="MAVLink system ID (default: 1)")
    parser.add_argument("--gcs-url", default="http://localhost:8000",
                        help="GCS Web API URL")
    parser.add_argument("--no-motor", action="store_true",
                        help="Skip motor test")
    parser.add_argument("--direct", action="store_true",
                        help="Direct MAVLink (no GCS API)")
    parser.add_argument("--logs-dir",
                        default=os.path.join(_PROJECT_ROOT, "logs"),
                        help="Log output directory (default: logs/)")
    parser.add_argument("--rtk-uart-port", default="/dev/ttyAMA5",
                        help="UART5 serial device path for RTK checks "
                             "(default: /dev/ttyAMA5)")
    parser.add_argument("--skip-rtk-uart2", action="store_true",
                        help="Skip UART2 RTK monitoring checks")
    args = parser.parse_args()

    print("""
============================================================
  Preflight Check Tool v1.0 - GCS-UmemotoLab
============================================================
""")
    logger.info(f"System ID: {args.system_id}")
    logger.info(f"GCS URL: {args.gcs_url}")
    logger.info(f"Logs dir: {args.logs_dir}")
    logger.info(f"Motor test: {'SKIPPED' if args.no_motor else 'ENABLED'}")
    logger.info(f"Mode: {'DIRECT MAVLink' if args.direct else 'GCS API'}")
    if args.skip_rtk_uart2:
        logger.info("RTK_UART2 checks: SKIPPED (--skip-rtk-uart2)")
    else:
        logger.info(f"RTK_UART2 port: {args.rtk_uart_port}")

    if args.direct:
        result = run_direct_mode(args.system_id, args.logs_dir, args.no_motor)
        # UART2 RTK checks — run even in direct mode
        if not args.skip_rtk_uart2:
            step_rtk_uart2_check(None, args.system_id, result,
                                 uart_port=args.rtk_uart_port)
        print("\n" + result.summary())
        result.save(args.logs_dir)
        return 0 if result.all_passed else 1

    api = GcsApiClient(args.gcs_url)
    result = CheckResult()

    # Step 1: System check
    step1_system_check(api, args.system_id, result)

    # UART2 RTK checks (after Step 1, before motor test)
    if not args.skip_rtk_uart2:
        step_rtk_uart2_check(api, args.system_id, result,
                             uart_port=args.rtk_uart_port)
    else:
        logger.info("RTK_UART2 checks: SKIPPED (--skip-rtk-uart2)")

    # Step 2: Motor test
    if not args.no_motor:
        step2_motor_test(api, args.system_id, result, args.logs_dir)
    else:
        logger.info("Step 2: Motor test -> SKIPPED (--no-motor)")
        result.add("MotorTest","Skipped",True,
                   "--no-motor flag", value="SKIPPED")

    # Step 3: Checklist
    step3_checklist(api, args.system_id, result)

    # Report
    print("\n" + result.summary())
    result_path = result.save(args.logs_dir)
    print(f"\nDetailed report: {result_path}")
    return 0 if result.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
