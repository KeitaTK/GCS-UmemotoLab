#!/usr/bin/env python3
"""GPS Error Collection with Fixed Base Station Coordinates.

Usage:
  python scripts/collect_with_fixed_base.py --count 30
"""

import argparse, csv, json, logging, math, socket, sys, threading, time
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("FixedBase-Collect")

BASE_LAT, BASE_LON, BASE_ALT = 36.0751418, 136.2133477, 10.50

FIX_TYPE_NAMES = {0:"NO_GPS",1:"NO_FIX",2:"2D_FIX",3:"3D_FIX",4:"DGPS",5:"RTK_FLOAT",6:"RTK_FIXED"}
METERS_PER_DEG_LAT = 111320.0

def lon_scale(lat): return METERS_PER_DEG_LAT * math.cos(math.radians(lat))
def h_error(lat1, lon1, lat2, lon2):
    dlat = (lat1 - lat2) * METERS_PER_DEG_LAT
    dlon = (lon1 - lon2) * lon_scale((lat1 + lat2) / 2)
    return math.sqrt(dlat**2 + dlon**2)
def v_error(alt1, alt2): return abs(alt1 - alt2)

def _extract_ws_text(buf):
    msgs, pos = [], 0
    while pos + 2 <= len(buf):
        opcode = buf[pos] & 0x0F
        if opcode not in (1, 2): pos += 1; continue
        pos += 1
        if pos >= len(buf): break
        masked = (buf[pos] & 0x80) != 0
        length = buf[pos] & 0x7F; pos += 1
        if length == 126:
            if pos + 2 > len(buf): break
            length = int.from_bytes(buf[pos:pos+2], "big"); pos += 2
        elif length == 127:
            if pos + 8 > len(buf): break
            length = int.from_bytes(buf[pos:pos+8], "big"); pos += 8
        mask = b""
        if masked:
            if pos + 4 > len(buf): break
            mask = buf[pos:pos+4]; pos += 4
        if pos + length > len(buf): break
        payload = buf[pos:pos+length]; pos += length
        if masked: payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        try: msgs.append(payload.decode("utf-8"))
        except UnicodeDecodeError: pass
    return msgs

def _find_gps(msg):
    gps = msg.get("GPS_RAW_INT") or msg.get("gps_raw_int")
    if not gps and isinstance(msg.get("gps"), dict): gps = msg["gps"]
    if not gps and "fix_type" in msg: gps = msg
    if not gps:
        for k, v in msg.items():
            if isinstance(v, dict) and "fix_type" in v: gps = v; break
    if not gps: return None
    ft = gps.get("fix_type", -1)
    sats = gps.get("satellites_visible", gps.get("sats", gps.get("satellites", 0)))
    lat_raw = gps.get("lat", gps.get("latitude", 0))
    lon_raw = gps.get("lon", gps.get("longitude", 0))
    alt_raw = gps.get("alt", gps.get("altitude", gps.get("alt_msl", 0)))
    lat = lat_raw / 1e7 if abs(lat_raw) > 180 else float(lat_raw) if lat_raw else 0.0
    lon = lon_raw / 1e7 if abs(lon_raw) > 180 else float(lon_raw) if lon_raw else 0.0
    alt = alt_raw / 1000.0 if abs(alt_raw) > 10000 else float(alt_raw) if alt_raw else 0.0
    return {"fix_type":ft,"satellites":sats,"lat":lat,"lon":lon,"alt":alt}

class GcsPoller:
    def __init__(self, base_url="http://localhost:8000", system_id=1):
        self.base_url = base_url.rstrip("/"); self.system_id = system_id
        import urllib.request
        self.urllib = urllib.request

    def get_telemetry(self, timeout=5.0):
        """Fetch GPS data via REST API (more reliable than WebSocket)."""
        try:
            req = self.urllib.Request(f"{self.base_url}/api/drones")
            req.add_header("Accept", "application/json")
            with self.urllib.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            drones = data.get("drones", [])
            for drone in drones:
                if drone.get("system_id") == self.system_id and drone.get("lat") is not None:
                    return {
                        "fix_type": drone.get("gps_fix", -1),
                        "satellites": drone.get("gps_sats", 0),
                        "lat": float(drone["lat"]),
                        "lon": float(drone["lon"]),
                        "alt": float(drone.get("alt", 0) or 0),
                    }
            return None
        except Exception as e:
            logger.debug(f"REST: {e}")
            return None

def collect(gcs, count=30, interval=2.0, max_duration=120.0):
    rows, start, deadline = [], time.monotonic(), time.monotonic() + max_duration
    logger.info(f"Base: {BASE_LAT:.7f}, {BASE_LON:.7f}, {BASE_ALT:.1f}m")
    logger.info(f"Target: {count} samples, interval={interval:.1f}s, max={max_duration:.0f}s")
    logger.info(f"{'='*70}")
    logger.info(f"{'#':>3}  {'FixType':>12}  {'Sats':>5}  {'HorizErr(m)':>12}  {'VertErr(m)':>10}")
    logger.info(f"{'='*70}")
    for i in range(count):
        if time.monotonic() > deadline: logger.warning(f"Time limit after {i}"); break
        iter_start = time.monotonic()
        p = gcs.get_telemetry(timeout=4.0)
        if p and p.get("lat", 0) != 0:
            he = h_error(BASE_LAT, BASE_LON, p["lat"], p["lon"])
            ve = v_error(BASE_ALT, p["alt"])
            fn = FIX_TYPE_NAMES.get(p.get("fix_type", -1), "?")
            row = {"timestamp":datetime.now().isoformat(),"fix_type":p.get("fix_type"),"fix_name":fn,
                   "satellites":p.get("satellites"),"lat_pixhawk":p["lat"],"lon_pixhawk":p["lon"],
                   "alt_pixhawk":p["alt"],"horizontal_error_m":he,"vertical_error_m":ve,
                   "base_lat":BASE_LAT,"base_lon":BASE_LON,"base_alt":BASE_ALT}
            rows.append(row)
            logger.info(f"{len(rows):>3}  {fn:>12}  {p['satellites']:>5}  {he:>12.3f}  {ve:>10.3f}")
        else:
            logger.warning(f"---  No Pixhawk data (sample {i+1})")
        elapsed = time.monotonic() - iter_start
        if (rem := interval - elapsed) > 0 and i < count - 1: time.sleep(rem)
    logger.info(f"{'='*70}")
    logger.info(f"Done: {len(rows)}/{count} samples in {time.monotonic()-start:.1f}s")
    return rows

def analyze(rows):
    if not rows: logger.error("No data"); return
    he = [r["horizontal_error_m"] for r in rows]
    ve = [r["vertical_error_m"] for r in rows]
    n = len(he)
    mh, mv = sum(he)/n, sum(ve)/n
    def sd(vals, m): return 0.0 if n<2 else math.sqrt(sum((v-m)**2 for v in vals)/(n-1))
    sh, sv = sd(he, mh), sd(ve, mv)
    fc = {}
    for r in rows: ft=r["fix_type"]; fc[ft]=fc.get(ft,0)+1
    print(f"\n{'='*60}\n  GPS Error Analysis (vs Fixed Base)\n{'='*60}")
    print(f"  Base: {BASE_LAT:.7f}, {BASE_LON:.7f}, {BASE_ALT:.1f}m  |  Samples: {n}")
    print(f"  --- Horizontal ---  Mean: {mh:.3f}m ({mh*100:.1f}cm)  StdDev: {sh:.3f}m ({sh*100:.1f}cm)  Min: {min(he):.3f}m  Max: {max(he):.3f}m")
    print(f"  --- Vertical -----  Mean: {mv:.3f}m ({mv*100:.1f}cm)  StdDev: {sv:.3f}m ({sv*100:.1f}cm)  Min: {min(ve):.3f}m  Max: {max(ve):.3f}m")
    print(f"  --- Fix Types ---")
    for ft in sorted(fc.keys()):
        name = FIX_TYPE_NAMES.get(ft,f"?{ft}")
        print(f"    {name:<15s} {ft}  {fc[ft]:5d} ({fc[ft]/n*100:5.1f}%)")
    rtk = [r for r in rows if r["fix_type"]==6]
    if rtk:
        rh = [r["horizontal_error_m"] for r in rtk]
        rv = [r["vertical_error_m"] for r in rtk]
        print(f"\n  ★ RTK FIXED {len(rtk)} samples:")
        print(f"     H mean={sum(rh)/len(rh)*100:.1f}cm max={max(rh)*100:.1f}cm")
        print(f"     V mean={sum(rv)/len(rv)*100:.1f}cm max={max(rv)*100:.1f}cm")
        if sum(rh)/len(rh) < 0.03: print(f"     ✅ 公称精度内 (<3cm)!")
        else: print(f"     ⚠️ 公称精度超過 (>3cm)")
    print("="*60)

def write_csv(rows, path):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    flds = ["timestamp","fix_type","fix_name","satellites","lat_pixhawk","lon_pixhawk","alt_pixhawk","horizontal_error_m","vertical_error_m","base_lat","base_lon","base_alt"]
    with open(p,"w",newline="") as f:
        w = csv.DictWriter(f, fieldnames=flds); w.writeheader()
        for r in rows: w.writerow({k:r.get(k,"") for k in flds})
    logger.info(f"Saved: {p} ({len(rows)} records)")

def main():
    p = argparse.ArgumentParser(description="GPS Error Collection — Fixed Base")
    p.add_argument("--gcs-url", default="http://localhost:8000")
    p.add_argument("--output","-o",default=None,help="CSV path")
    p.add_argument("--count","-n",type=int,default=30)
    p.add_argument("--interval",type=float,default=2.0)
    p.add_argument("--max-duration",type=float,default=120.0)
    args = p.parse_args()
    if args.output is None: args.output = f"logs/compare_fixed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    logger.info(f"=== GPS Error Collection (Fixed Base) ===")
    gcs = GcsPoller(args.gcs_url)
    test = gcs.get_telemetry(timeout=5.0)
    if test:
        fn = FIX_TYPE_NAMES.get(test.get("fix_type",-1),"?")
        logger.info(f"Pixhawk: fix={test.get('fix_type')}({fn}) sats={test.get('satellites')} lat={test.get('lat',0):.7f} lon={test.get('lon',0):.7f}")
    else:
        logger.error("No Pixhawk GPS data! Check Raspi/GCS/bridge."); sys.exit(1)
    try:
        rows = collect(gcs, args.count, args.interval, args.max_duration)
        if rows: write_csv(rows, args.output); analyze(rows)
        else: print("No data"); sys.exit(1)
    except KeyboardInterrupt: logger.info("Interrupted")

if __name__ == "__main__": main()
