#!/usr/bin/env python3
"""GPS Compare Data Analyzer — RTK FIXED時の比較データを統計分析"""
import argparse, csv, math, statistics, sys
from collections import Counter
from pathlib import Path

def latlon_to_meters(lat, lon, ref_lat, ref_lon):
    dlat = lat - ref_lat
    dlon = lon - ref_lon
    north = dlat * 111320.0
    east = dlon * 111320.0 * math.cos(math.radians(ref_lat))
    return north, east

def analyze_csv(csv_path):
    path = Path(csv_path)
    if not path.exists():
        print(f"ERROR: File not found: {csv_path}")
        sys.exit(1)
    rows = []
    with open(path, "r") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    if not rows:
        print("ERROR: No data rows")
        sys.exit(1)
    print(f"=== GPS Compare Data Analysis ===")
    print(f"File: {csv_path}")
    print(f"Total rows: {len(rows)}")
    headers = list(rows[0].keys())
    has_pixhawk = "lat_p" in headers and any(r.get("lat_p","").strip() for r in rows)
    if has_pixhawk:
        fix_ps = [int(r.get("fix_p",-1)) for r in rows if r.get("fix_p","").strip()]
        lats_p = [float(r["lat_p"]) for r in rows if r.get("lat_p","").strip()]
        lons_p = [float(r["lon_p"]) for r in rows if r.get("lon_p","").strip()]
        alts_p = [float(r["alt_p"]) for r in rows if r.get("alt_p","").strip()]
        print(f"\n--- Pixhawk GPS ---")
        print(f"  Samples: {len(lats_p)}")
        if fix_ps:
            fc = Counter(fix_ps)
            fn = {3:"3D_FIX",4:"DGPS",5:"RTK_FLOAT",6:"RTK_FIXED"}
            for ft, cnt in sorted(fc.items()):
                print(f"  fix_type={ft} ({fn.get(ft,'?')}): {cnt}")
        if len(lats_p) >= 2:
            rlat = statistics.mean(lats_p)
            rlon = statistics.mean(lons_p)
            h_cm = []
            for lat, lon in zip(lats_p, lons_p):
                n, e = latlon_to_meters(lat, lon, rlat, rlon)
                h_cm.append(math.sqrt(n**2+e**2)*100)
            print(f"\n  --- Position Stability ---")
            print(f"  Mean Lat: {rlat:.8f}")
            print(f"  Mean Lon: {rlon:.8f}")
            if alts_p:
                malt = statistics.mean(alts_p)
                v_cm = [(a-malt)*100 for a in alts_p]
                print(f"  Mean Alt: {malt:.2f} m")
                if len(v_cm) >= 2:
                    print(f"  Vertical StdDev: {statistics.stdev(v_cm):.2f} cm")
            if len(h_cm) >= 2:
                print(f"  Horizontal StdDev: {statistics.stdev(h_cm):.2f} cm")
            print(f"  Horizontal RMS: {math.sqrt(statistics.mean([e**2 for e in h_cm])):.2f} cm")
            print(f"  Horizontal Max: {max(h_cm):.2f} cm")
            print(f"  Horizontal Min: {min(h_cm):.2f} cm")
    return rows

def main():
    p = argparse.ArgumentParser(description="Analyze GPS compare CSV")
    p.add_argument("csv_path")
    args = p.parse_args()
    analyze_csv(args.csv_path)

if __name__ == "__main__":
    main()
