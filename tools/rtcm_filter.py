#!/usr/bin/env python3
"""
rtcm_filter.py - RTCM3 filter/analyzer using pyrtcm.RTCMReader

Modes:
  Post-analysis: python3 rtcm_filter.py -i raw.bin [-o filtered.bin]
  Live serial:   python3 rtcm_filter.py --serial /dev/ttyACM0 [--mavlink udp:...]
"""
import argparse, sys, io, time
from collections import Counter
from datetime import datetime
from pyrtcm import RTCMReader

RTCM_NAMES = {
    "1005":"Station XYZ", "1074":"GPS MSM4", "1084":"GLO MSM4",
    "1094":"GAL MSM4", "1124":"BDS MSM4", "1230":"GLO Bias",
    "1019":"GPS Eph", "1020":"GLO Eph", "4072":"u-blox Proprietary",
}

def analyze_file(input_path, output_path=None, dump_first=0):
    with open(input_path, "rb") as f:
        raw_data = f.read()
    print(f"[*] Input: {input_path} ({len(raw_data)} bytes)\n")

    stream = io.BytesIO(raw_data)
    rtr = RTCMReader(stream)
    mt_ctr = Counter()
    first_tow = last_tow = None
    filtered = bytearray()
    all_msgs = []

    for raw, parsed in rtr:
        mt = parsed.identity
        mt_ctr[mt] += 1
        filtered.extend(raw)
        all_msgs.append((mt, raw, parsed))
        if hasattr(parsed, "DF004"):
            tow = parsed.DF004
            if first_tow is None: first_tow = tow
            last_tow = tow

    duration_s = 0
    if first_tow is not None:
        d = (last_tow - first_tow) / 1000.0
        duration_s = d if d >= 0 else d + 604800

    total = sum(mt_ctr.values())
    print("=" * 55)
    print(f"{'RTCM Message Statistics':^55}")
    print("=" * 55)
    for mt in sorted(mt_ctr, key=lambda x: int(x)):
        c = mt_ctr[mt]
        n = RTCM_NAMES.get(str(mt), "Unknown")
        print(f"  MT {mt:>5s}  {c:>4d} msgs ({100*c/total:5.1f}%)  {n}")
    print(f"\n  Total RTCM msgs: {total}")
    print(f"  Filtered size:   {len(filtered)} bytes")
    print(f"  Removed:         {len(raw_data)-len(filtered)} bytes (NMEA/UBX/CRC-err)")
    print(f"  Duration:        {duration_s:.1f}s")
    if duration_s > 0:
        print(f"  Avg bitrate:     {len(filtered)*8/duration_s:.0f} bps")

    print(f"\n{'RTK Required Messages Check':=^55}")
    checks = [
        ("1005", "Station Coordinates", "MISSING - base position unknown!"),
        ("1074", "GPS MSM4",            "MISSING - no GPS observations!"),
        ("1019", "GPS Ephemeris",       "missing (F9P may use 4072 instead)"),
    ]
    for mt, desc, warn in checks:
        ok = mt in mt_ctr
        print(f"  {'[OK]' if ok else '[!!]'}  {desc}  {'✅' if ok else warn}")

    if dump_first > 0:
        print(f"\n{'First ' + str(dump_first) + ' Messages':=^55}")
        for i, (mt, raw, parsed) in enumerate(all_msgs[:dump_first]):
            info = ""
            if hasattr(parsed, "DF003"): info += f" stn={parsed.DF003}"
            if hasattr(parsed, "DF004"): info += f" tow={parsed.DF004}"
            print(f"  [{i:3d}] MT={mt:<5s} {RTCM_NAMES.get(str(mt),''):<25s} len={len(raw):>3d}{info}")

    if output_path:
        with open(output_path, "wb") as f:
            f.write(filtered)
        print(f"\n[*] Saved filtered RTCM: {output_path} ({len(filtered)} bytes)")

def live_filter(serial_port, baudrate, mavlink_target=None,
                output_path=None, verbose=False):
    import serial
    ser = serial.Serial(serial_port, baudrate, timeout=1)
    print(f"[*] Serial: {serial_port} @ {baudrate}")
    out_f = open(output_path, "wb") if output_path else None
    mav = None
    if mavlink_target:
        from pymavlink import mavutil
        mav = mavutil.mavlink_connection(mavlink_target)
        print(f"[*] MAVLink: {mavlink_target}")
    print("[*] Filtering... Ctrl+C to stop\n")
    rtr, cnt, t0 = RTCMReader(ser), 0, time.time()
    try:
        for raw, parsed in rtr:
            cnt += 1
            if out_f: out_f.write(raw)
            if mav: _mav_send(mav, raw)
            if verbose:
                mt = parsed.identity
                print(f"  {datetime.now():%H:%M:%S} #{cnt:4d} MT={mt:<5s} {RTCM_NAMES.get(str(mt),'')} ({len(raw)}B)")
    except KeyboardInterrupt:
        pass
    finally:
        elapsed = time.time()-t0
        print(f"\n[*] Done. {cnt} msgs in {elapsed:.1f}s ({cnt/elapsed:.1f}/s)")
        if out_f: out_f.close()
        ser.close()

def _mav_send(mav, data):
    CS = 180
    nf = (len(data)+CS-1)//CS
    for i in range(0, len(data), CS):
        c = data[i:i+CS]
        fid = i//CS
        flags = (1|(fid<<1)) if nf>1 else 0
        mav.mav.gps_rtcm_data_send(flags, len(c), c.ljust(CS, b'\x00'))

def main():
    p = argparse.ArgumentParser(description="RTCM3 filter/analyzer (pyrtcm)")
    p.add_argument("-i", "--input", help="Input .bin file")
    p.add_argument("-o", "--output", help="Output filtered .bin")
    p.add_argument("--serial", help="Serial port")
    p.add_argument("--baud", type=int, default=38400)
    p.add_argument("--mavlink", help="MAVLink target (udp:...)")
    p.add_argument("--dump", type=int, default=0)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    if args.input:
        analyze_file(args.input, args.output, args.dump)
    elif args.serial:
        live_filter(args.serial, args.baud, args.mavlink, args.output, args.verbose)
    else:
        p.print_help()

if __name__ == "__main__":
    main()
