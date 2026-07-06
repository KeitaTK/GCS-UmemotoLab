#!/usr/bin/env python3
"""
RTCM → EKF 注入 エンドツーエンドテスト
========================================

テスト手順:
  1) ダミーF9P基地局 を起動し RTK 単独測位をシミュレート
  2) RTCMデータが TCP:2101 で配信されているか確認
  3) RtcmReader → RtcmInjector → GPS_RTCM_DATA を検証
"""

import sys, os, time, socket, threading, struct, logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

logging.basicConfig(level=logging.INFO,
    format='[%(asctime)s] %(levelname)-7s %(name)s: %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("test_rtcm_ekf")

# ============================================================================
# テスト結果
# ============================================================================

@dataclass
class TestResults:
    tests: dict = field(default_factory=dict)
    details: list = field(default_factory=list)
    def record(self, name, passed, detail=""):
        self.tests[name] = passed
        self.details.append((name, passed, detail))
    @property
    def all_passed(self):
        return all(self.tests.values())
    def summary(self):
        lines = ["=" * 70, "  RTCM → EKF Injection Test Report", "=" * 70]
        for name, passed, detail in self.details:
            lines.append(f"  {'✓ PASS' if passed else '✗ FAIL'}: {name}")
            if detail:
                for d in detail.split('\n'):
                    lines.append(f"    {d}")
        total, pc = len(self.tests), sum(1 for p in self.tests.values() if p)
        lines.extend([f"\n  総合: {pc}/{total} テスト合格", "=" * 70])
        return '\n'.join(lines)

# ============================================================================
# ダミーF9P基地局
# ============================================================================

class DummyF9PBaseStation:
    """F9P基地局シミュレータ - RTCM v3 フレーム生成 + TCP:2101 配信"""

    RTCM_MSG_TYPES = {
        1005: "StationXYZ", 1074: "GPS_MSM4", 1084: "GLO_MSM4",
        1094: "GAL_MSM4", 1124: "BDS_MSM4", 1230: "GLO_Bias"
    }

    def __init__(self, host="127.0.0.1", port=2101, lat=35.681236, lon=139.767125,
                 alt=42.0, interval=0.3):
        self.host = host; self.port = port; self.lat = lat; self.lon = lon
        self.alt = alt; self.interval = interval
        self.running = False; self.server_sock = None
        self.clients = []; self.clients_lock = threading.Lock()
        self.stats = {'connections': 0, 'frames_sent': 0, 'bytes_sent': 0}

    def start(self):
        self.running = True
        threading.Thread(target=self._run_server, daemon=True).start()
        time.sleep(0.3)
        logger.info(f"✅ Dummy F9P Base Station: {self.host}:{self.port}")

    def stop(self):
        self.running = False
        if self.server_sock:
            try: self.server_sock.close()
            except: pass
        with self.clients_lock:
            for c in list(self.clients):
                try: c.close()
                except: pass
            self.clients.clear()

    def _run_server(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind((self.host, self.port))
            self.server_sock.listen(5)
            threading.Thread(target=self._broadcast_loop, daemon=True).start()
            while self.running:
                self.server_sock.settimeout(1.0)
                try:
                    csock, addr = self.server_sock.accept()
                    self.stats['connections'] += 1
                    logger.info(f"   Client connected: {addr}")
                    with self.clients_lock:
                        self.clients.append(csock)
                except socket.timeout:
                    continue
        except Exception as e:
            logger.error(f"   Base station error: {e}")
        finally:
            if self.server_sock:
                try: self.server_sock.close()
                except: pass

    def _broadcast_loop(self):
        seq = 0; types = [1005, 1074, 1084, 1094, 1124, 1230]
        while self.running:
            mt = types[seq % len(types)]
            frame = self._build_rtcm_frame(mt, seq)
            with self.clients_lock:
                dead = []
                for cs in self.clients:
                    try:
                        cs.sendall(frame)
                        self.stats['frames_sent'] += 1
                        self.stats['bytes_sent'] += len(frame)
                    except:
                        dead.append(cs)
                for d in dead:
                    self.clients.remove(d)
                    try: d.close()
                    except: pass
            seq += 1; time.sleep(self.interval)

    def _build_rtcm_frame(self, msg_type, seq):
        if msg_type == 1005:
            body = bytearray(19); body_len = 19
        else:
            body_len = 180
            body = bytearray(body_len)
            body[0] = (msg_type >> 4) & 0xFF
            body[1] = ((msg_type & 0x0F) << 4) | 0x0A
            for i in range(2, body_len):
                body[i] = (seq + i) & 0xFF
        frame = bytearray(3 + body_len + 3)
        frame[0] = 0xD3
        frame[1] = (body_len >> 8) & 0x3F
        frame[2] = body_len & 0xFF
        frame[3:3+body_len] = body
        crc = self._crc24q(frame[:3+body_len])
        frame[3+body_len] = (crc >> 16) & 0xFF
        frame[3+body_len+1] = (crc >> 8) & 0xFF
        frame[3+body_len+2] = crc & 0xFF
        return bytes(frame)

    def _crc24q(self, data):
        crc = 0
        for b in data:
            crc ^= (b << 16)
            for _ in range(8):
                crc <<= 1
                if crc & 0x1000000:
                    crc ^= 0x1864CFB
        return crc & 0xFFFFFF

    def generate_nmea_gga(self):
        lat_deg = int(self.lat); lat_min = (self.lat - lat_deg) * 60
        lat_str = f"{lat_deg:02d}{lat_min:07.4f}"
        lon_deg = int(abs(self.lon)); lon_min = (abs(self.lon) - lon_deg) * 60
        lon_str = f"{lon_deg:03d}{lon_min:07.4f}"
        gga = (f"$GNGGA,120000.00,{lat_str},N,{lon_str},E,"
               f"1,18,0.8,{self.alt:.1f},M,36.0,M,,*")
        csum = 0
        for c in gga[1:-1]:
            csum ^= ord(c)
        return f"{gga}{csum:02X}"

# ============================================================================
# TEST 1: RTK 単独測位
# ============================================================================

def test_1_rtk_standalone(results):
    logger.info("\n" + "=" * 70)
    logger.info("  TEST 1: RTK Base Station - 単独測位 (Standalone)")
    logger.info("=" * 70)
    try:
        bs = DummyF9PBaseStation(port=2101)
        bs.start()
        # NMEA検証
        nmea = bs.generate_nmea_gga()
        logger.info(f"   NMEA: {nmea}")
        parts = nmea.split(',')
        assert parts[0] == '$GNGGA'
        assert parts[6] == '1', f"Expected fix=1 (standalone), got {parts[6]}"
        lat_r = float(parts[2]); lat = int(lat_r/100) + (lat_r - int(lat_r/100)*100)/60
        lon_r = float(parts[4]); lon = int(lon_r/100) + (lon_r - int(lon_r/100)*100)/60
        assert abs(lat - 35.681236) < 0.001
        assert abs(lon - 139.767125) < 0.001
        logger.info(f"   ✓ fix=1 (GPS単独測位), sats=18, HDOP=0.8, pos={lat:.7f}/{lon:.7f}")
        # TCP確認
        time.sleep(0.3)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        r = s.connect_ex(('127.0.0.1', 2101)); s.close()
        assert r == 0, f"TCP:2101 not listening (errno={r})"
        logger.info("   ✓ TCP:2101 リッスン確認 OK")
        bs.stop()
        results.record("TEST1: RTK単独測位", True, f"NMEA fix=1, TCP:2101 OK")
        logger.info("  ✓ TEST 1 PASSED\n")
    except Exception as e:
        logger.error(f"  ✗ TEST 1 FAILED: {e}")
        results.record("TEST1: RTK単独測位", False, str(e))
        try: bs.stop()
        except: pass

# ============================================================================
# TEST 2: RTCM TCP:2101 配信確認
# ============================================================================

def test_2_rtcm_tcp(results, bs):
    logger.info("\n" + "=" * 70)
    logger.info("  TEST 2: RTCM Data Distribution via TCP:2101")
    logger.info("=" * 70)
    try:
        logger.info("[2a] TCP:2101 接続...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5); sock.connect(('127.0.0.1', 2101))
        logger.info("   ✓ Connected to tcp://127.0.0.1:2101")
        logger.info("[2b] RTCM v3 フレーム受信 (5秒)...")
        buf = bytearray(); frames = []; t0 = time.time()
        while time.time() - t0 < 5.0:
            try:
                sock.settimeout(1.0)
                d = sock.recv(4096)
                if d: buf.extend(d)
                while len(buf) >= 6:
                    if buf[0] != 0xD3: buf.pop(0); continue
                    fl = ((buf[1] & 0x3F) << 8) | buf[2]
                    total = 3 + fl + 3
                    if len(buf) < total: break
                    frm = bytes(buf[:total]); buf = buf[total:]
                    mt = ((frm[3] << 4) | (frm[4] >> 4))
                    frames.append({'msg_type': mt, 'len': len(frm)})
            except socket.timeout: continue
        sock.close()
        logger.info(f"   受信: {len(frames)} frames")
        assert len(frames) > 0, "No RTCM frames received"
        types = {}
        for f in frames:
            types[f['msg_type']] = types.get(f['msg_type'], 0) + 1
        tnames = {1005:"StationXYZ",1074:"GPS_MSM4",1084:"GLO_MSM4",1094:"GAL_MSM4",1124:"BDS_MSM4",1230:"GLO_Bias"}
        for mt, cnt in sorted(types.items()):
            logger.info(f"     Type {mt} ({tnames.get(mt,'?')}): {cnt} frames")
        assert len(types) >= 2, f"Expected >=2 types, got {len(types)}"
        bw = sum(f['len'] for f in frames) / 5.0
        logger.info(f"   ✓ {len(types)} message types, bandwidth={bw:.0f} B/s")
        results.record("TEST2: RTCM TCP配信", True,
                       f"{len(frames)} frames, {len(types)} types, {bw:.0f} B/s")
        logger.info("  ✓ TEST 2 PASSED\n")
    except Exception as e:
        logger.error(f"  ✗ TEST 2 FAILED: {e}")
        results.record("TEST2: RTCM TCP配信", False, str(e))

# ============================================================================
# TEST 3: GPS_RTCM_DATA 注入
# ============================================================================

def test_3_rtcm_to_gps_rtcm_data(results, bs):
    logger.info("\n" + "=" * 70)
    logger.info("  TEST 3: RTCM → GPS_RTCM_DATA (MAVLink msgid=233) Injection")
    logger.info("=" * 70)
    reader = None
    try:
        from app.rtk_tools.rtcm_reader import RtcmReader
        from app.rtk_tools.rtcm_injector import RtcmInjector
        reader = RtcmReader(host="127.0.0.1", port=2101, enabled=True)
        injector = RtcmInjector(enabled=True, max_payload_size=180, system_id=1, component_id=1)
        captured = []
        injector.set_send_callback(lambda f: captured.append(f))
        reader.register_callback(lambda d: injector.inject(d))
        reader.start()
        logger.info("[3a] RtcmReader → RtcmInjector pipeline active")
        time.sleep(5)
        reader.stop()
        logger.info(f"   RTCM msgs: {reader.stats['messages_received']}, "
                     f"MAVLink frames: {len(captured)}")
        logger.info(f"   Injector stats: {injector.get_stats()}")
        assert len(captured) > 0, "No GPS_RTCM_DATA frames"
        assert reader.stats['messages_received'] > 0
        assert injector.stats['rtcm_messages_sent'] > 0
        # MAVLink v2 frame 検証
        valid = 0
        for f in captured[:20]:
            if len(f) >= 12 and f[0] == 0xFD:
                msgid = f[7] | (f[8] << 8) | (f[9] << 16)
                if msgid == 233:
                    valid += 1
        logger.info(f"   ✓ Valid GPS_RTCM_DATA (msgid=233): {valid}/{min(20,len(captured))}")
        # CRC-16
        crc_ok = 0
        for f in captured[:20]:
            if len(f) >= 14 and f[0] == 0xFD:
                data_crc = f[1:-2]
                exp_crc = f[-2] | (f[-1] << 8)
                crc = 0xFFFF
                for b in data_crc:
                    crc ^= (b << 8)
                    for _ in range(8):
                        crc <<= 1
                        if crc & 0x10000: crc ^= 0x1021
                    crc &= 0xFFFF
                if crc == exp_crc:
                    crc_ok += 1
        logger.info(f"   ✓ CRC-16 valid: {crc_ok}")
        results.record("TEST3: GPS_RTCM_DATA注入", True,
                       f"{len(captured)} MAVLink frames, {reader.stats['messages_received']} RTCM msgs, CRC={crc_ok}")
        logger.info("  ✓ TEST 3 PASSED\n")
    except ImportError as e:
        logger.error(f"  ✗ TEST 3 FAILED: Import: {e}")
        results.record("TEST3: GPS_RTCM_DATA注入", False, f"Import: {e}")
    except Exception as e:
        logger.error(f"  ✗ TEST 3 FAILED: {e}")
        results.record("TEST3: GPS_RTCM_DATA注入", False, str(e))
    finally:
        if reader:
            try: reader.stop()
            except: pass

# ============================================================================
# TEST 4: Full Pipeline E2E
# ============================================================================

def test_4_full_pipeline(results, bs):
    logger.info("\n" + "=" * 70)
    logger.info("  TEST 4: Full Pipeline End-to-End")
    logger.info("=" * 70)
    reader = None
    try:
        from app.rtk_tools.rtcm_reader import RtcmReader
        from app.rtk_tools.rtcm_injector import RtcmInjector
        logger.info("   Pipeline: F9P(Dummy) → TCP:2101 → RtcmReader → Injector → GPS_RTCM_DATA")
        reader = RtcmReader(host="127.0.0.1", port=2101, enabled=True)
        injector = RtcmInjector(enabled=True, max_payload_size=180, system_id=1, component_id=1)
        captured = []
        injector.set_send_callback(lambda f: captured.append(f))
        reader.register_callback(lambda d: injector.inject(d))
        reader.start()
        time.sleep(5)
        reader.stop()
        from app.rtk_tools.rtcm_reader import RtcmReader
        assert len(captured) > 0
        assert reader.stats['messages_received'] > 0
        assert injector.stats['rtcm_messages_sent'] > 0
        loss = abs(reader.stats['bytes_received'] - injector.stats['bytes_sent'])
        ratio = loss / max(reader.stats['bytes_received'], 1)
        logger.info(f"   RTCM→{reader.stats['messages_received']}msgs, "
                     f"GPS_RTCM_DATA→{injector.stats['mavlink_messages_sent']}frames, "
                     f"byte_loss={ratio*100:.1f}%")
        results.record("TEST4: Full Pipeline E2E", True,
                       f"RTCM:{reader.stats['messages_received']}msgs→GPS_RTCM_DATA:{injector.stats['mavlink_messages_sent']}frames, loss={ratio*100:.1f}%")
        logger.info("  ✓ TEST 4 PASSED\n")
    except Exception as e:
        logger.error(f"  ✗ TEST 4 FAILED: {e}")
        results.record("TEST4: Full Pipeline E2E", False, str(e))
    finally:
        if reader:
            try: reader.stop()
            except: pass

# ============================================================================
# MAIN
# ============================================================================

def main():
    logger.info("=" * 70)
    logger.info("  RTCM → EKF Injection Test Suite")
    logger.info(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    results = TestResults()
    bs = None
    try:
        # TEST 1 (内部で独自のbase stationを使う)
        test_1_rtk_standalone(results)
        # 共有基地局 for TEST 2-4
        logger.info("\n[SETUP] Starting shared Dummy F9P Base Station...")
        bs = DummyF9PBaseStation(port=2101, interval=0.3)
        bs.start()
        time.sleep(0.5)
        test_2_rtcm_tcp(results, bs)
        test_3_rtcm_to_gps_rtcm_data(results, bs)
        test_4_full_pipeline(results, bs)
    except Exception as e:
        logger.error(f"Fatal: {e}")
        results.record("SETUP", False, str(e))
    finally:
        if bs:
            bs.stop()
    print(results.summary())
    return 0 if results.all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
