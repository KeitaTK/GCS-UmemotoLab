#!/usr/bin/env python3
"""
GPS Comparison Data Collector — Sample 4 Rapid Collection Script

u-blox (NMEA serial) と Pixhawk (GCS API/MAVLink) のGPSデータを
同期的に取得し、compare CSV 形式で保存します。

【RTCM接続確認を最優先】
 - RTCM Connected が確認できたら即座にデータ取得開始
 - 1分以内に20サンプル収集を目標

【使用例】
  python scripts/gps_compare_collect.py \
      --ublox /dev/tty.usbmodem113301 \
      --gcs-url http://100.75.83.95:8000 \
      --output logs/compare_sample4.csv \
      --count 20

【CSVフォーマット】
  fix_u,sats_u,lat_u,lon_u,alt_u,fix_p,sats_p,lat_p,lon_p,alt_p
  u = u-blox, p = Pixhawk
"""

import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("GPS-Compare")

FIX_TYPE_NAMES = {
    0: "NO_GPS", 1: "NO_FIX", 2: "2D_FIX", 3: "3D_FIX",
    4: "DGPS", 5: "RTK_FLOAT", 6: "RTK_FIXED",
    7: "STATIC", 8: "PPP",
}

CSV_HEADER = "fix_u,sats_u,lat_u,lon_u,alt_u,fix_p,sats_p,lat_p,lon_p,alt_p"


def parse_nmea_gga(line: str) -> dict | None:
    """Parse $GPGGA or $GNGGA NMEA sentence.

    Returns dict with fix_quality, satellites, lat, lon, alt or None.
    """
    line = line.strip()
    if not (line.startswith("$GPGGA") or line.startswith("$GNGGA")):
        return None

    try:
        parts = line.split(",")
        if len(parts) < 15:
            return None

        fix_quality = int(parts[6]) if parts[6] else 0
        num_sats = int(parts[7]) if parts[7] else 0

        lat_str, lat_dir = parts[2], parts[3]
        lon_str, lon_dir = parts[4], parts[5]
        alt_str = parts[9]

        lat_dd = None
        lon_dd = None
        alt_m = None

        if lat_str and lon_str:
            lat_dd = float(lat_str[:2]) + float(lat_str[2:]) / 60.0
            if lat_dir == "S":
                lat_dd = -lat_dd
            lon_dd = float(lon_str[:3]) + float(lon_str[3:]) / 60.0
            if lon_dir == "W":
                lon_dd = -lon_dd

        if alt_str:
            alt_m = float(alt_str)

        # Map NMEA fix_quality to MAVLink-like fix_type
        # NMEA: 0=None, 1=GPS, 2=DGPS, 4=RTK Fixed, 5=RTK Float
        # MAVLink: 0=NO_GPS, 3=3D_FIX, 4=DGPS, 5=RTK_FLOAT, 6=RTK_FIXED
        fix_map = {0: 0, 1: 3, 2: 4, 4: 6, 5: 5}
        fix_type = fix_map.get(fix_quality, fix_quality)

        return {
            "fix_type": fix_type,
            "satellites": num_sats,
            "lat": lat_dd,
            "lon": lon_dd,
            "alt": alt_m,
        }
    except (ValueError, IndexError) as e:
        logger.debug(f"NMEA parse error: {e} | line: {line[:80]}")
        return None


class UbloxReader:
    """Read u-blox NMEA from serial port."""

    def __init__(self, port: str, baudrate: int = 38400, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser = None
        self._latest: dict | None = None

    def open(self):
        import serial
        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        logger.info(f"u-blox serial opened: {self.port} @ {self.baudrate}")

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()

    def poll(self, timeout_s: float = 3.0) -> dict | None:
        """Read until a valid GGA sentence is found (or timeout)."""
        import serial as _serial
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                line = self._ser.readline().decode("ascii", errors="ignore")
                result = parse_nmea_gga(line)
                if result and result.get("lat") is not None:
                    self._latest = result
                    return result
            except _serial.SerialException:
                break
            except Exception as e:
                logger.debug(f"u-blox read: {e}")
class GcsPoller:
    """Poll Pixhawk GPS data via GCS HTTP API/WebSocket."""

    def __init__(self, base_url: str, system_id: int = 1):
        self.base_url = base_url.rstrip("/")
        self.system_id = system_id

    def get_telemetry(self) -> dict | None:
        """Get drone telemetry via GCS WebSocket.

        Returns dict with fix_type, satellites, lat, lon, alt or None.
        """
        import socket
        import threading

        result = {"gps": None}

        def _ws_connect():
            try:
                url = self.base_url.replace("http://", "").replace("https://", "")
                if ":" in url:
                    host, port_str = url.rsplit(":", 1)
                    port = int(port_str)
                else:
                    host, port = url, 8000

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((host, port))

                key = "dGhlIHNhbXBsZSBub25jZQ=="
                request = (
                    f"GET /ws HTTP/1.1\r\n"
                    f"Host: {host}:{port}\r\n"
                    f"Upgrade: websocket\r\n"
                    f"Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {key}\r\n"
                    f"Sec-WebSocket-Version: 13\r\n"
                    f"\r\n"
                )
                sock.sendall(request.encode())

                response = b""
                while b"\r\n\r\n" not in response:
                    chunk = sock.recv(4096)
                    if not chunk:
                        return
                    response += chunk

                if b"101" not in response:
                    return

                start = time.monotonic()
                buffer = b""
                while time.monotonic() - start < 5.0:
                    try:
                        sock.settimeout(1.0)
                        data = sock.recv(65535)
                        if data:
                            buffer += data
                            msgs = self._ws_extract_text(buffer)
                            for msg_str in msgs:
                                try:
                                    msg = json.loads(msg_str)
                                    gps = self._find_gps(msg)
                                    if gps:
                                        result["gps"] = gps
                                        return
                                except json.JSONDecodeError:
                                    continue
                    except socket.timeout:
                        continue
            except Exception as e:
                logger.debug(f"WebSocket: {e}")
            finally:
                try:
                    sock.close()
                except:
                    pass

        t = threading.Thread(target=_ws_connect, daemon=True)
        t.start()
        t.join(timeout=7.0)
        return result["gps"]

    @staticmethod
    def _ws_extract_text(buffer: bytes) -> list[str]:
        """Extract text payloads from WebSocket frames."""
        messages = []
        pos = 0
        while pos + 2 <= len(buffer):
            first = buffer[pos]
            opcode = first & 0x0F
            if opcode not in (1, 2):
                pos += 1
                continue
            pos += 1
            if pos >= len(buffer):
                break
            second = buffer[pos]
            pos += 1
            masked = (second & 0x80) != 0
            length = second & 0x7F
            if length == 126:
                if pos + 2 > len(buffer):
                    break
                length = int.from_bytes(buffer[pos:pos+2], "big")
                pos += 2
            elif length == 127:
                if pos + 8 > len(buffer):
                    break
                length = int.from_bytes(buffer[pos:pos+8], "big")
                pos += 8
            mask = b""
            if masked:
                if pos + 4 > len(buffer):
                    break
                mask = buffer[pos:pos+4]
                pos += 4
            if pos + length > len(buffer):
                break
            payload = buffer[pos:pos+length]
            pos += length
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            try:
                messages.append(payload.decode("utf-8"))
            except UnicodeDecodeError:
                pass
        return messages

    def _find_gps(self, msg: dict) -> dict | None:
        """Find GPS_RAW_INT-like fields in a telemetry message."""
        if "GPS_RAW_INT" in msg:
            gps = msg["GPS_RAW_INT"]
        elif "gps_raw_int" in msg:
            gps = msg["gps_raw_int"]
        elif "gps" in msg and isinstance(msg["gps"], dict):
            gps = msg["gps"]
        elif "fix_type" in msg and ("lat" in msg or "latitude" in msg):
            gps = msg
        else:
            for key, val in msg.items():
                if isinstance(val, dict):
                    if "GPS_RAW_INT" in val:
                        gps = val["GPS_RAW_INT"]
                        break
                    if "fix_type" in val:
                        gps = val
                        break
            else:
                return None
        if gps is None:
            return None

        fix_type = gps.get("fix_type", -1)
        sats = gps.get("satellites_visible",
                       gps.get("sats", gps.get("satellites", 0)))

        lat_raw = gps.get("lat", gps.get("latitude", 0))
        lon_raw = gps.get("lon", gps.get("longitude", 0))
        alt_raw = gps.get("alt", gps.get("altitude", gps.get("alt_msl", 0)))

        if abs(lat_raw) > 180 and isinstance(lat_raw, (int, float)):
            lat_dd = lat_raw / 1e7
        else:
            lat_dd = float(lat_raw) if lat_raw else 0.0

        if abs(lon_raw) > 180 and isinstance(lon_raw, (int, float)):
            lon_dd = lon_raw / 1e7
        else:
            lon_dd = float(lon_raw) if lon_raw else 0.0

        if abs(alt_raw) > 10000 and isinstance(alt_raw, (int, float)):
            alt_m = alt_raw / 1000.0
        else:
            alt_m = float(alt_raw) if alt_raw else 0.0

        return {
            "fix_type": fix_type,
            "satellites": sats,
            "lat": lat_dd,
            "lon": lon_dd,
            "alt": alt_m,
        }


def collect_samples(
    ublox: UbloxReader,
    gcs: GcsPoller,
    count: int = 20,
    interval: float = 2.0,
    max_duration: float = 60.0,
) -> list[dict]:
    """Collect synchronized GPS samples from u-blox and Pixhawk."""
    rows = []
    start_time = time.monotonic()
    deadline = start_time + max_duration

    logger.info(f"Target: {count} samples in {max_duration:.0f}s (interval={interval:.1f}s)")
    logger.info(f"{'='*60}")
    logger.info(f"{'#':>3}  {'u-blox':>12}  {'Pixhawk':>12}  {'FixU':>6}  {'FixP':>6}")
    logger.info(f"{'='*60}")

    for i in range(count):
        if time.monotonic() > deadline:
            logger.warning(f"Time limit reached after {i} samples")
            break

        iter_start = time.monotonic()
        u_data = ublox.poll(timeout_s=2.0)
        p_data = gcs.get_telemetry()

        if u_data and p_data:
            row = {
                "fix_u": u_data.get("fix_type", ""),
                "sats_u": u_data.get("satellites", ""),
                "lat_u": u_data.get("lat", ""),
                "lon_u": u_data.get("lon", ""),
                "alt_u": u_data.get("alt", ""),
                "fix_p": p_data.get("fix_type", ""),
                "sats_p": p_data.get("satellites", ""),
                "lat_p": p_data.get("lat", ""),
                "lon_p": p_data.get("lon", ""),
                "alt_p": p_data.get("alt", ""),
            }
            rows.append(row)
            fu = FIX_TYPE_NAMES.get(u_data.get("fix_type"), "?")
            fp = FIX_TYPE_NAMES.get(p_data.get("fix_type"), "?")
            logger.info(
                f"{len(rows):>3}  ({u_data['satellites']:>2}sats)      "
                f"({p_data['satellites']:>2}sats)      {fu:>6}  {fp:>6}"
            )
        else:
            missing = []
            if not u_data:
                missing.append("u-blox")
            if not p_data:
                missing.append("Pixhawk")
            logger.warning(f"---  No data: {', '.join(missing)}")

        elapsed = time.monotonic() - iter_start
        remaining = interval - elapsed
        if remaining > 0 and i < count - 1:
            time.sleep(remaining)

    elapsed_total = time.monotonic() - start_time
    logger.info(f"{'='*60}")
    logger.info(f"Done: {len(rows)}/{count} samples in {elapsed_total:.1f}s")
    return rows


def write_csv(rows: list[dict], output_path: str):
    """Write collected rows to CSV file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER.split(","))
        for row in rows:
            writer.writerow([
                row.get("fix_u", ""),
                row.get("sats_u", ""),
                f"{row['lat_u']:.8f}" if row.get("lat_u") not in (None, "") else "",
                f"{row['lon_u']:.8f}" if row.get("lon_u") not in (None, "") else "",
                f"{row['alt_u']:.1f}" if row.get("alt_u") not in (None, "") else "",
                row.get("fix_p", ""),
                row.get("sats_p", ""),
                f"{row['lat_p']:.8f}" if row.get("lat_p") not in (None, "") else "",
                f"{row['lon_p']:.8f}" if row.get("lon_p") not in (None, "") else "",
                f"{row['alt_p']:.1f}" if row.get("alt_p") not in (None, "") else "",
            ])
    logger.info(f"Data saved: {path} ({len(rows)} records)")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="GPS Comparison Data Collector — Sample 4 Rapid Collection",
    )
    parser.add_argument("--ublox", "-u", required=True,
                        help="u-blox serial port (e.g. /dev/tty.usbmodem113301)")
    parser.add_argument("--ublox-baud", type=int, default=38400,
                        help="u-blox baud rate (default: 38400)")
    parser.add_argument("--gcs-url", default="http://100.75.83.95:8000",
                        help="GCS API base URL")
    parser.add_argument("--output", "-o", default="logs/compare_sample4.csv",
                        help="Output CSV path")
    parser.add_argument("--count", "-n", type=int, default=20,
                        help="Number of samples (default: 20)")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Polling interval seconds (default: 2.0)")
    parser.add_argument("--max-duration", type=float, default=60.0,
                        help="Max collection time seconds (default: 60)")
    parser.add_argument("--system-id", type=int, default=1,
                        help="Pixhawk MAVLink system ID (default: 1)")

    args = parser.parse_args()

    if args.count * args.interval > args.max_duration:
        logger.warning(
            f"May exceed time limit: {args.count}*{args.interval}s="
            f"{args.count*args.interval}s > {args.max_duration}s max"
        )

    logger.info("=== GPS Comparison Data Collector ===")
    logger.info(f"  u-blox port:  {args.ublox}")
    logger.info(f"  GCS URL:      {args.gcs_url}")
    logger.info(f"  Output:       {args.output}")
    logger.info(f"  Samples:      {args.count} (max {args.max_duration}s)")

    ublox = UbloxReader(args.ublox, baudrate=args.ublox_baud)
    try:
        ublox.open()
    except Exception as e:
        logger.error(f"Failed to open u-blox: {e}")
        sys.exit(1)

    gcs = GcsPoller(args.gcs_url, system_id=args.system_id)

    logger.info(f"Checking GCS connection at {args.gcs_url}...")
    gps_test = gcs.get_telemetry()
    if gps_test:
        fn = FIX_TYPE_NAMES.get(gps_test.get("fix_type", -1), "?")
        logger.info(
            f"Pixhawk GPS: fix={gps_test.get('fix_type')}({fn}), "
            f"sats={gps_test.get('satellites')}, "
            f"lat={gps_test.get('lat', 0):.6f}, "
            f"lon={gps_test.get('lon', 0):.6f}"
        )
    else:
        logger.warning("Could not get Pixhawk GPS from GCS. Retrying...")

    try:
        rows = collect_samples(
            ublox, gcs,
            count=args.count,
            interval=args.interval,
            max_duration=args.max_duration,
        )
        if rows:
            path = write_csv(rows, args.output)
            print(f"\n✅ Done: {path} ({len(rows)} records)")
        else:
            print("\n❌ No valid samples collected.")
            print("   Check: u-blox serial, GCS /api/connect, RTCM connection")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        ublox.close()


if __name__ == "__main__":
    main()
