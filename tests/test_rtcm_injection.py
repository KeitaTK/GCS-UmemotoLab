#!/usr/bin/env python3
"""
Minimal test: send GPS_RTCM_DATA frames to a drone via UDP without starting
the base station. Isolates whether RTCM frame format (v1 vs v2 magic byte)
or injection rate causes the MAVLink connection to drop.

Usage:
  # Default: send 10 frames to 127.0.0.1:14550, 50ms delay
  python tests/test_rtcm_injection.py

  # Custom target, rate, count
  python tests/test_rtcm_injection.py --target 127.0.0.1:14552 --delay 0.1 --count 5

  # Use v1 frames (0xFE magic) to reproduce the issue
  python tests/test_rtcm_injection.py --force-v1

  # Use v2 frames (0xFD magic) — the fix
  python tests/test_rtcm_injection.py --force-v2

  # Burst mode: no delay between frames
  python tests/test_rtcm_injection.py --no-delay
"""

import argparse
import logging
import socket
import time
from pymavlink import mavutil

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_rtcm_injection")

# ── Dummy RTCM data (type 1074, 150 bytes, realistic) ──────────────────────
DUMMY_RTCM = bytes([
    0xD3, 0x00, 0x13, 0x3E, 0x80, 0x00, 0x00, 0x00,
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80,
    0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
    0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00, 0x11,
    0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99,
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
    0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF,
    0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF,
    0xFE, 0xDC, 0xBA, 0x98, 0x76, 0x54, 0x32, 0x10,
    0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80,
    0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
    0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00, 0x11,
    0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99,
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
    0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF,
    0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF,
    0xFE, 0xDC, 0xBA, 0x98, 0x76, 0x54, 0x32, 0x10,
    0xFF, 0xEE, 0xDD, 0xCC, 0xBB, 0xAA,
])


def build_rtcm_frame(mav, rtcm_data: bytes) -> list:
    """Build one or more GPS_RTCM_DATA frames from RTCM payload."""
    max_payload = 180
    data_len = len(rtcm_data)
    frames = []
    start = 0

    while start < data_len:
        length = min(data_len - start, max_payload)
        chunk = rtcm_data[start:start + length]

        # Flags
        flags = 0
        if start + length < data_len:
            flags |= 0x01  # more fragments follow
        fragment_id = (start // max_payload) & 0x03
        flags |= (fragment_id << 1)

        # Pad to 180 bytes
        padded = bytearray(chunk).ljust(max_payload, b'\x00')

        msg = mav.gps_rtcm_data_encode(flags, length, bytes(padded))
        frame = msg.pack(mav)
        frames.append(frame)
        start += length

    return frames


def parse_target(target_str: str) -> tuple:
    """Parse 'host:port' into (host, port)."""
    if ':' in target_str:
        host, port = target_str.rsplit(':', 1)
        return host, int(port)
    return target_str, 14550


def main():
    parser = argparse.ArgumentParser(
        description="Minimal GPS_RTCM_DATA injection test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", default="127.0.0.1:14550", help="UDP target host:port")
    parser.add_argument("--count", type=int, default=10, help="Number of frames to send")
    parser.add_argument("--delay", type=float, default=0.05, help="Delay between frames (sec)")
    parser.add_argument("--no-delay", action="store_true", help="No inter-frame delay")
    parser.add_argument("--force-v1", action="store_true", help="Use v1 frames (0xFE magic)")
    parser.add_argument("--force-v2", action="store_true", help="Use v2 frames (0xFD magic)")
    parser.add_argument("--large-rtcm", action="store_true", help="Use >180 byte RTCM to force fragmentation")
    args = parser.parse_args()

    if args.force_v1:
        use_v2 = False
        vlabel = "v1 (0xFE)"
    elif args.force_v2:
        use_v2 = True
        vlabel = "v2 (0xFD)"
    else:
        use_v2 = True
        vlabel = "v2 (0xFD, default)"

    target_host, target_port = parse_target(args.target)
    delay = 0.0 if args.no_delay else args.delay

    rtcm_data = DUMMY_RTCM
    if args.large_rtcm:
        rtcm_data = (DUMMY_RTCM * 3)[:400]

    logger.info("=" * 60)
    logger.info("GPS_RTCM_DATA Injection Test")
    logger.info(f"  Target:     {target_host}:{target_port}")
    logger.info(f"  Frames:     {args.count}")
    logger.info(f"  Delay:      {delay}s {'(no delay)' if args.no_delay else ''}")
    logger.info(f"  Format:     {vlabel}")
    logger.info(f"  RTCM bytes: {len(rtcm_data)}")
    logger.info("=" * 60)

    if use_v2:
        from pymavlink.dialects.v20 import ardupilotmega as mavlink2
        mav = mavlink2.MAVLink(
            bytearray(), srcSystem=255, srcComponent=240,
            use_native=False,
        )
    else:
        mav = mavutil.mavlink.MAVLink(
            bytearray(), srcSystem=255, srcComponent=240,
            use_native=False,
        )

    frames = build_rtcm_frame(mav, rtcm_data)
    logger.info(
        f"RTCM {len(rtcm_data)} bytes -> {len(frames)} MAVLink frame(s)")
    if frames:
        f0 = frames[0]
        logger.info(
            f"First frame: len={len(f0)}, magic=0x{f0[0]:02X}, "
            f"first 10 hex={f0[:10].hex(' ')}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (target_host, target_port)

    logger.info(f"Starting injection ({args.count} frames)...")
    sent = 0
    try:
        for i in range(args.count):
            for j, frame in enumerate(frames):
                sock.sendto(frame, target)
                sent += 1
                if j > 0 and delay > 0:
                    time.sleep(delay)
            if delay > 0:
                time.sleep(delay)
        logger.info(f"Done. Sent {sent} MAVLink frames to {target_host}:{target_port}")
    except KeyboardInterrupt:
        logger.info(f"Interrupted. Sent {sent} frames.")
    except Exception as e:
        logger.error(f"Send error: {e}", exc_info=True)
    finally:
        sock.close()
    logger.info("Test complete.")


if __name__ == "__main__":
    main()

