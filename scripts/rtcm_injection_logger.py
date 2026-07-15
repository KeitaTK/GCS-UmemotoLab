#!/usr/bin/env python3
"""RTCM Injection Logger — 基地局TCPからRTCMフレームを読み取り注入ログを記録"""
import csv
import os
import socket
import sys
import time


INJECTION_LOG_DIR = "logs"
INJECTION_LOG_FILE = os.path.join(INJECTION_LOG_DIR, "rtcm_injection.log")
RTCM_PREAMBLE = 0xD3


def main():
    base_host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    base_port = int(sys.argv[2]) if len(sys.argv) > 2 else 2101
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    os.makedirs(INJECTION_LOG_DIR, exist_ok=True)
    f = open(INJECTION_LOG_FILE, "a", newline="")
    w = csv.writer(f)
    if os.path.getsize(INJECTION_LOG_FILE) == 0:
        w.writerow(["timestamp", "frame_count", "cumulative_bytes", "frames_per_min", "bytes_per_minute", "errors"])
        f.flush()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((base_host, base_port))
        print(f"Connected to {base_host}:{base_port}")
    except Exception as e:
        print(f"Connection failed: {e}")
        f.close()
        sys.exit(1)

    total_frames = 0
    total_bytes = 0
    errors = 0
    start_time = time.time()
    last_log_time = start_time
    last_frames = 0
    last_bytes = 0
    buffer = bytearray()

    try:
        while time.time() - start_time < duration:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                buffer.extend(data)
            except socket.timeout:
                continue

            # Extract RTCM frames
            while len(buffer) >= 6:
                if buffer[0] != RTCM_PREAMBLE:
                    buffer.pop(0)
                    continue
                reserved = buffer[1] >> 6
                frame_len = ((buffer[1] & 0x3F) << 8) | buffer[2]
                total = 6 + frame_len
                if len(buffer) < total:
                    break
                frame = bytes(buffer[:total])
                buffer = buffer[total:]
                total_frames += 1
                total_bytes += len(frame)

            # Periodic logging
            now = time.time()
            if now - last_log_time >= 5:
                elapsed = now - last_log_time
                df = total_frames - last_frames
                db = total_bytes - last_bytes
                fpm = (df / elapsed) * 60.0 if elapsed > 0 else 0
                bpm = (db / elapsed) * 60.0 if elapsed > 0 else 0
                last_frames = total_frames
                last_bytes = total_bytes
                last_log_time = now
                ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
                w.writerow([ts, total_frames, total_bytes, f"{fpm:.1f}", f"{bpm:.1f}", errors])
                f.flush()
                print(f"[{ts}] frames={total_frames}, bytes={total_bytes}, fpm={fpm:.1f}, bpm={bpm:.1f}")

    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        f.close()
        print(f"\nDone. {total_frames} frames, {total_bytes} bytes logged to {INJECTION_LOG_FILE}")


if __name__ == "__main__":
    main()
