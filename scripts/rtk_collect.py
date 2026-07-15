#!/usr/bin/env python3
"""RTK Error Collector – HTTP API based, fast polling."""
import csv, json, math, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

METERS_PER_DEG_LAT = 111320.0
FIX_NAMES = {0:"NO_GPS",1:"NO_FIX",2:"2D_FIX",3:"3D_FIX",4:"DGPS",5:"RTK_FLOAT",6:"RTK_FIXED",7:"STATIC",8:"PPP"}
BASE_LAT, BASE_LON, BASE_ALT = 36.075714, 136.213740, 46.9

def lon_scale(lat):
    return METERS_PER_DEG_LAT * math.cos(math.radians(lat))

def stat(vals):
    if not vals: return {"count":0}
    m = sum(vals)/len(vals)
    var = sum((x-m)**2 for x in vals)/(len(vals)-1) if len(vals)>1 else 0
    sv = sorted(vals)
    return {"count":len(vals),"mean":round(m,4),"std":round(math.sqrt(var),4),
            "min":round(sv[0],4),"max":round(sv[-1],4),
            "rms":round(math.sqrt(sum(x**2 for x in vals)/len(vals)),4)}

count, interval = 60, 1.0
rows, t0 = [], time.monotonic()
print(f"RTK Error Collection: {count} samples @ {interval}s")

for i in range(count):
    try:
        resp = urllib.request.urlopen("http://localhost:8000/api/drones", timeout=3)
        data = json.loads(resp.read())
        drone = next((d for d in data.get("drones",[]) if d.get("system_id")==1), None)
        if not drone: continue
        fix = drone.get("gps_fix",-1)
        sats = drone.get("gps_sats",0)
        lat = drone.get("lat") or 0
        lon = drone.get("lon") or 0
        alt = drone.get("alt") or 0
        hdop = drone.get("hdop",99)
        dlat_m = (lat-BASE_LAT)*METERS_PER_DEG_LAT
        dlon_m = (lon-BASE_LON)*lon_scale(BASE_LAT)
        dalt_m = alt-BASE_ALT
        h_err = math.sqrt(dlat_m**2+dlon_m**2)
        el = time.monotonic()-t0
        fn = FIX_NAMES.get(fix,f"UNK({fix})")
        print(f"  {len(rows)+1:>3} {el:>5.1f}s {fn:>14} sats={sats:>2} err={h_err:.3f}m dalt={dalt_m:.1f}m")
        rows.append({"timestamp":round(el,1),"fix_p":fix,"fix_name":fn,"sats_p":sats,"hdop_p":hdop,
                     "lat_p":lat,"lon_p":lon,"alt_p":alt,
                     "base_lat":BASE_LAT,"base_lon":BASE_LON,"base_alt":BASE_ALT,
                     "delta_lat_m":round(dlat_m,3),"delta_lon_m":round(dlon_m,3),
                     "delta_alt_m":round(dalt_m,3),"horizontal_error_m":round(h_err,3)})
    except Exception as e:
        print(f"  ERR: {e}")
    time.sleep(interval)

t_elapsed = time.monotonic()-t0
if not rows:
    print("ERROR: no data"); sys.exit(1)

# Save CSV
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_path = Path("logs")/f"rtk_error_{ts}.csv"
csv_path.parent.mkdir(parents=True,exist_ok=True)
header = ["timestamp","fix_p","fix_name","sats_p","hdop_p","lat_p","lon_p","alt_p",
          "base_lat","base_lon","base_alt","delta_lat_m","delta_lon_m","delta_alt_m","horizontal_error_m"]
with open(csv_path,"w",newline="") as f:
    w=csv.writer(f); w.writerow(header)
    for r in rows: w.writerow([r.get(k,"") for k in header])

# Analyze
n=len(rows)
all_h=[r["horizontal_error_m"] for r in rows]
all_v=[abs(r["delta_alt_m"]) for r in rows]
rf_rows=[r for r in rows if r["fix_p"]==6]
rfl_rows=[r for r in rows if r["fix_p"]==5]
fix_dist={}
for r in rows:
    ft=r["fix_p"]; fix_dist[ft]=fix_dist.get(ft,0)+1
timeline=[]; seen=set()
for r in rows:
    ft=r["fix_p"]
    if ft not in seen and ft>=3:
        timeline.append({"t":r["timestamp"],"fix":ft,"name":FIX_NAMES.get(ft,"UNKNOWN")})
        seen.add(ft)
rtkf=6 in fix_dist; rtkfl=5 in fix_dist
conv={}
if rtkfl:
    for r in rows:
        if r["fix_p"]>=5: conv["rtk_float_or_better_s"]=r["timestamp"]; break
if rtkf:
    for r in rows:
        if r["fix_p"]==6: conv["rtk_fixed_s"]=r["timestamp"]; break
within=conv.get("rtk_float_or_better_s",999)<=60

analysis={"timestamp":datetime.now().isoformat(),
    "base_station":{"mode":"FIXED (manual)","lat":BASE_LAT,"lon":BASE_LON,"alt":BASE_ALT},
    "total_samples":n,"duration_sec":round(t_elapsed,1),
    "rtk_float_achieved":rtkfl,"rtk_fixed_achieved":rtkf,"within_1min_fix":within,
    "convergence_times":conv,
    "fix_p_distribution":{FIX_NAMES.get(k,f"UNK({k})"):v for k,v in sorted(fix_dist.items())},
    "fix_p_timeline":timeline,
    "horizontal_error_all":stat(all_h),"vertical_error_all":stat(all_v),
    "horizontal_error_rtk_fixed":stat([r["horizontal_error_m"] for r in rf_rows]),
    "vertical_error_rtk_fixed":stat([abs(r["delta_alt_m"]) for r in rf_rows]),
    "horizontal_error_rtk_float":stat([r["horizontal_error_m"] for r in rfl_rows]),
    "vertical_error_rtk_float":stat([abs(r["delta_alt_m"]) for r in rfl_rows])}

json_path=Path("logs")/f"rtk_analysis_{ts}.json"
with open(json_path,"w") as f:
    json.dump(analysis,f,indent=2,ensure_ascii=False)

# Print summary
print(f"\n{'='*60}")
print(f"RTK ANALYSIS: {n} samples, {t_elapsed:.1f}s")
print(f"RTK Float: {'YES' if rtkfl else 'NO'}, RTK Fixed: {'YES' if rtkf else 'NO'}")
print(f"1min FIX: {'PASS' if within else 'FAIL'}")
for k,v in conv.items(): print(f"  {k}: {v}s")
he=analysis["horizontal_error_all"]
print(f"HorizErr: mean={he['mean']}m std={he['std']}m max={he['max']}m rms={he['rms']}m")
ve=analysis["vertical_error_all"]
print(f"VertErr:  mean={ve['mean']}m std={ve['std']}m max={ve['max']}m")
hr=analysis.get("horizontal_error_rtk_fixed",{})
if hr.get("count",0)>0:
    print(f"RTK Fixed HorizErr: mean={hr['mean']}m std={hr['std']}m")
print(f"\nFix distribution:")
for name,cnt in sorted(analysis["fix_p_distribution"].items()):
    pct=cnt/n*100; print(f"  {name:<18s} {cnt:>4d} ({pct:5.1f}%) {'#'*int(pct/2)}")
print(f"{'='*60}")
print(f"CSV: {csv_path}")
print(f"JSON: {json_path}")
