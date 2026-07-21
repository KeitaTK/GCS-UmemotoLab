#!/usr/bin/env python3
"""
MAVLink RTCM Injector — Test #5
UART2 HW故障時のフォールバック: RTCM→GPS_RTCM_DATA→Pixhawk→DroneCAN→F9P UART1

経路: 基地局TCP:2101 → MAVLink GPS_RTCM_DATA → UDP:14552
      → Bridge → SSH tunnel → mavlink-router → Pixhawk → DroneCAN → F9P UART1
"""
import argparse
import logging
import socket
import struct
import sys
import time

logger = logging.getLogger("MAVLinkRTCM")

MAVLINK_MAGIC = 0xFD
GPS_RTCM_DATA_MSGID = 233
MAX_RTCM_DATA_LEN = 180


class MavlinkRtcmInjector:
    """Read RTCM from base station TCP and inject via MAVLink GPS_RTCM_DATA."""

    def __init__(self, base_host="127.0.0.1", base_port=2101,
                 mavlink_target="127.0.0.1:14552"):
        self.base_host = base_host
        self.base_port = base_port
        host, port = mavlink_target.rsplit(":", 1)
        self.mav_target = (host, int(port))
        self._sysid = 255  # GCS sender ID
        self._compid = 0
        self._seq = 0
        self._mav_sock = None
        self.rtcm_frames_in = 0
        self.rtcm_bytes_in = 0
        self.mavlink_frames_out = 0
        self.start_time = 0.0

    def _crc16(self, data):
        crc = 0xFFFF
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                crc <<= 1
                if crc & 0x10000:
                    crc ^= 0x1021
            crc &= 0xFFFF
        return crc

    def _build_frame(self, msgid, payload):
        """Build MAVLink v2 frame: magic(1)+len(1)+flags(2)+seq(1)+sysid(1)+compid(1)+msgid(3)+payload+CRC(2)"""
        frame = bytearray()
        frame.append(MAVLINK_MAGIC)
        frame.append(len(payload))
        frame.append(0x00)  # incompat_flags
        frame.append(0x00)  # compat_flags
        seq = self._seq & 0xFF
        self._seq = (self._seq + 1) & 0xFF
        frame.append(seq)
        frame.append(self._sysid)
        frame.append(self._compid)
        frame.append(msgid & 0xFF)
        frame.append((msgid >> 8) & 0xFF)
        frame.append((msgid >> 16) & 0xFF)
        frame.extend(payload)
        crc = self._crc16(frame[1:])
        frame.append(crc & 0xFF)
        frame.append((crc >> 8) & 0xFF)
        return bytes(frame)

    def send_gps_rtcm_data(self, rtcm_chunk):
        """Send one GPS_RTCM_DATA (msgid=233). Payload: flags(1)+len(1)+data."""
        chunk = rtcm_chunk[:MAX_RTCM_DATA_LEN]
        payload = struct.pack('<BB', 0, len(chunk)) + chunk
        while len(payload) < 4:
            payload += b'\x00'
        frame = self._build_frame(GPS_RTCM_DATA_MSGID, payload)
        if self._mav_sock:
            self._mav_sock.sendto(frame, self.mav_target)
            self.mavlink_frames_out += 1

    def run(self, duration=0, max_frames=0):
        self._mav_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.start_time = time.monotonic()

        logger.info(f"Base station: {self.base_host}:{self.base_port}")
        logger.info(f"MAVLink target: {self.mav_target[0]}:{self.mav_target[1]}")

        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.settimeout(10)
        tcp_sock.connect((self.base_host, self.base_port))
        logger.info("Connected to base station")

        buf = bytearray()
        last_stats = time.monotonic()

        try:
            while True:
                if duration > 0 and time.monotonic() - self.start_time > duration:
                    break
                if max_frames > 0 and self.rtcm_frames_in >= max_frames:
                    break

                try:
                    tcp_sock.settimeout(0.5)
                    data = tcp_sock.recv(4096)
                    if not data:
                        break
                    buf.extend(data)
                except socket.timeout:
                    pass

                # Extract RTCM3 frames (preamble 0xD3)
                while len(buf) >= 6:
                    if buf[0] != 0xD3:
                        buf.pop(0)
                        continue
                    frame_len = ((buf[1] & 0x03) << 8) | buf[2]
                    total = 6 + frame_len
                    if len(buf) < total:
                        break
                    self.send_gps_rtcm_data(bytes(buf[:total]))
                    self.rtcm_frames_in += 1
                    self.rtcm_bytes_in += total
                    buf = buf[total:]

                now = time.monotonic()
                if now - last_stats >= 5:
                    elapsed = now - self.start_time
                    fps = self.rtcm_frames_in / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"RTCM: {self.rtcm_frames_in} frames "
                        f"({self.rtcm_bytes_in}B, {fps:.1f}fps) | "
                        f"MAVLink: {self.mavlink_frames_out} msgs"
                    )
                    last_stats = now

        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            tcp_sock.close()
            self._mav_sock.close()
            elapsed = time.monotonic() - self.start_time
            logger.info(
                f"Done: {self.rtcm_frames_in} RTCM ({self.rtcm_bytes_in}B), "
                f"{self.mavlink_frames_out} MAVLink msgs in {elapsed:.1f}s"
            )


def main():
    p = argparse.ArgumentParser(description="MAVLink RTCM Injector")
    p.add_argument("--base-host", default="127.0.0.1")
    p.add_argument("--base-port", type=int, default=2101)
    p.add_argument("--mavlink-target", default="127.0.0.1:14552")
    p.add_argument("--duration", type=float, default=0, help="seconds (0=forever)")
    p.add_argument("--max-frames", type=int, default=0, help="max RTCM frames")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    inj = MavlinkRtcmInjector(
        base_host=args.base_host,
        base_port=args.base_port,
        mavlink_target=args.mavlink_target,
    )
    inj.run(duration=args.duration, max_frames=args.max_frames)


if __name__ == "__main__":
    main()
