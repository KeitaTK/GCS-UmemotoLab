"""
RTCM -> MAVLink GPS_RTCM_DATA standalone injector (manual v2 frames + CRC_EXTRA).

Usage:
    python rtk_tools/rtcm_injector_v2.py --serial COM10 --target 192.168.11.19:14550
"""
import argparse, logging, socket, sys, threading, time
from queue import Queue, Empty
from typing import Optional
import serial

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("rtcm_injector_v2")

MSG_ID = 233
CRC_EXTRA = 35
MAX_PAYLOAD = 180


from pymavlink.dialects.v20.ardupilotmega import x25crc

def _crc16(data: bytes) -> int:
    c = x25crc(data)
    return c.crc


def build_frame(flags: int, length: int, data: bytes, sysid: int = 1, compid: int = 1, seq: int = 0) -> bytes:
    payload = bytearray(1 + 1 + MAX_PAYLOAD)
    payload[0] = flags & 0xFF
    payload[1] = length & 0xFF
    payload[2:] = data[:MAX_PAYLOAD].ljust(MAX_PAYLOAD, b'\x00')
    f = bytearray()
    f.append(0xFD); f.append(len(payload) & 0xFF); f.append(0x00); f.append(0x00)
    f.append(0x00); f.append(seq & 0xFF); f.append(sysid & 0xFF); f.append(compid & 0xFF)
    f.append(MSG_ID & 0xFF); f.append((MSG_ID >> 8) & 0xFF); f.append((MSG_ID >> 16) & 0xFF)
    f.extend(payload)
    crc = _crc16(f[1:] + bytes([CRC_EXTRA]))
    f.append(crc & 0xFF); f.append((crc >> 8) & 0xFF)
    return bytes(f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--serial", default="COM10")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--target", default="127.0.0.1:14550")
    p.add_argument("--sysid", type=int, default=1)
    args = p.parse_args()
    host, _, port = args.target.partition(":")
    port = int(port) if port else 14550
    logger.info(f"Serial={args.serial} Target={host}:{port} SysID={args.sysid}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (host, port)

    try:
        ser = serial.Serial(args.serial, args.baud, timeout=1)
        logger.info(f"Opened {args.serial}")
    except Exception as e:
        logger.error(f"Serial open failed: {e}")
        sys.exit(1)

    buf = bytearray()
    seq = 0
    frames_sent = 0
    try:
        while True:
            data = ser.read(1024)
            if data:
                buf.extend(data)
                while len(buf) >= 6:
                    if buf[0] != 0xD3:
                        buf.pop(0)
                        continue
                    flen = ((buf[1] & 0x3F) << 8) | buf[2]
                    total = 6 + flen
                    if len(buf) < total:
                        break
                    rtcm = bytes(buf[:total])
                    buf = buf[total:]
                    start = 0
                    dlen = len(rtcm)
                    while start < dlen:
                        chunk_len = min(dlen - start, MAX_PAYLOAD)
                        chunk = rtcm[start:start + chunk_len]
                        flags = 0
                        if start + chunk_len < dlen:
                            flags |= 0x01
                        flags |= ((start // MAX_PAYLOAD) & 0x03) << 1
                        padded = bytearray(chunk).ljust(MAX_PAYLOAD, b'\x00')
                        frame = build_frame(flags, chunk_len, bytes(padded), sysid=args.sysid, seq=seq)
                        seq = (seq + 1) & 0xFF
                        sock.sendto(frame, target)
                        frames_sent += 1
                        start += chunk_len
                    logger.debug(f"RTCM {len(rtcm)}B sent, total={frames_sent}")
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        sock.close()
        logger.info(f"Done. {frames_sent} frames sent.")


if __name__ == "__main__":
    main()
