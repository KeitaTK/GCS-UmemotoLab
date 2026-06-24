#!/usr/bin/env python3
"""u-blox Survey-In configuration script for RTK base station.

Configures u-blox (ZED-F9P) to run Survey-In mode, which averages its
position over time to achieve cm-level accuracy. Once complete, the u-blox
outputs RTCM with a precisely known base position, enabling RTK Fixed (fix=6)
on the rover.

Usage:
  python scripts/ublox_survey_in.py [--port /dev/tty.usbmodemXXXX] [--min-time 120] [--target-acc 2.0]
"""

import argparse, struct, serial, time

def ubx_checksum(msg: bytes) -> bytes:
    ck_a = ck_b = 0
    for b in msg:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return bytes([ck_a, ck_b])

def send_ubx(ser: serial.Serial, cls: int, mid: int, payload: bytes = b''):
    header = struct.pack('<BBBB', 0xB5, 0x62, cls, mid)
    body = header[2:] + payload
    ck = ubx_checksum(body)
    pkt = header + payload + ck
    ser.write(pkt)
    return pkt

def read_ubx(ser: serial.Serial, cls: int, mid: int, timeout: float = 3.0) -> bytes | None:
    start = time.time()
    buf = b''
    target = bytes([0xB5, 0x62, cls, mid])
    while time.time() - start < timeout:
        b = ser.read(ser.in_waiting or 1)
        if b:
            buf += b
        idx = buf.find(target)
        if idx >= 0 and len(buf) >= idx + 8:
            pLen = buf[idx+4] | (buf[idx+5] << 8)
            total = 8 + pLen
            if len(buf) >= idx + total:
                return buf[idx:idx+total]
        time.sleep(0.05)
    return None

def main():
    parser = argparse.ArgumentParser(description='u-blox Survey-In configuration')
    parser.add_argument('--port', default='/dev/tty.usbmodem113301', help='Serial port')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate')
    parser.add_argument('--min-time', type=int, default=120, help='Minimum observation time (seconds)')
    parser.add_argument('--target-acc', type=float, default=2.0, help='Target accuracy (meters)')
    args = parser.parse_args()

    print(f'Opening {args.port} @ {args.baud}...')
    ser = serial.Serial(args.port, args.baud, timeout=1)
    time.sleep(0.5)
    ser.reset_input_buffer()

    # --- Configure Survey-In (UBX-CFG-TMODE3) ---
    # mode=1: Survey-In, svInMinDur=min_time (seconds), svInAccLimit=target_acc*10000 (0.1mm)
    payload = struct.pack('<BBHII',
        0,           # version
        0,           # reserved1
        0,           # flags (LLA)
        1,           # mode = 1 (Survey-In)
        0,           # reserved2
    )
    payload += struct.pack('<II',
        args.min_time,                       # svInMinDur (seconds)
        int(args.target_acc * 10000),        # svInAccLimit (0.1mm)
    )
    payload += b'\x00' * 16  # remaining reserved fields
    send_ubx(ser, 0x06, 0x71, payload)
    print(f'Survey-In configured: min_time={args.min_time}s, target_acc={args.target_acc}m')

    # --- Enable RTCM output on port ---
    # Enable RTCM 1074,1084,1094,1124 (MSM4 for GPS,GLONASS,Galileo,BeiDou) + 1005,1230
    rtcm_msgs = [
        struct.pack('<BBBBB', 0, 1, 0, 1, 1),  # 1005 - station coordinates
        struct.pack('<BBBBB', 0, 2, 0, 1, 1),  # 1074 - GPS MSM4
        struct.pack('<BBBBB', 0, 3, 0, 1, 1),  # 1084 - GLONASS MSM4
        struct.pack('<BBBBB', 0, 4, 0, 1, 0),  # 1094 - Galileo MSM4
    ]
    for msg in rtcm_msgs:
        send_ubx(ser, 0x06, 0x01, b'\x02\x10' + msg)
    print('RTCM output enabled (MSM4 + 1005)')

    # --- Save config to flash ---
    send_ubx(ser, 0x06, 0x09, b'\x00\x00\x00\x00')
    time.sleep(1)
    print('Config saved to flash.')

    # --- Monitor Survey-In progress ---
    print('\nMonitoring Survey-In progress (Ctrl+C to stop)...')
    print('  Time  Accuracy   Status')
    print('  ----  --------   ------')
    try:
        while True:
            resp = read_ubx(ser, 0x06, 0x71, timeout=2.0)
            if resp and len(resp) >= 42:
                (ver, r1, flags, mode, r2, dur, limit, obs, valid, active) = struct.unpack(
                    '<BBHIIIIIHB', resp[6:36])
                acc_mm = struct.unpack('<I', resp[36:40])[0] if len(resp) >= 40 else 0
                acc_m = acc_mm / 10000.0
                status = 'IN_PROGRESS'
                if valid:
                    status = '✅ VALID (RTK-ready!)'
                print(f'  {dur:5d}s  {acc_m:7.3f}m  {status}')
                if valid:
                    print('\n=== Survey-In complete! u-blox is now RTK-ready. ===')
                    break
            time.sleep(5)
    except KeyboardInterrupt:
        print('\nMonitoring stopped.')

    ser.close()

if __name__ == '__main__':
    main()
