#!/usr/bin/env python3
"""
NTRIP Relay Server
- Connects to an NTRIP caster and receives RTCM data
- Listens on a TCP port for clients (e.g. Raspi via Tailscale)
- Forwards RTCM data to all connected clients
- Sends periodic GGA sentences to the NTRIP caster

Usage: ntrip_relay.py --config config/rtk_ntrip_relay.yml
"""
import argparse
import base64
import logging
import signal
import socket
import sys
import threading
import time
from datetime import datetime

import yaml

logger = logging.getLogger("ntrip_relay")
_running = True
_clients = []
_clients_lock = threading.Lock()


def load_config(path):
    with open(path, "r") as fh:
        return yaml.safe_load(fh)


def make_gga(lat, lon, alt):
    """Build an NMEA GGA sentence."""
    t = datetime.utcnow().strftime("%H%M%S.00")
    la = abs(lat)
    lat_d, lat_m = int(la), (la - int(la)) * 60
    lo = abs(lon)
    lon_d, lon_m = int(lo), (lo - int(lo)) * 60
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    body = (
        f"GPGGA,{t},{lat_d:02d}{lat_m:07.4f},{ns},"
        f"{lon_d:03d}{lon_m:07.4f},{ew},1,12,1.0,{alt:.1f},M,0.0,M,,"
    )
    ck = 0
    for c in body:
        ck ^= ord(c)
    return f"${body}*{ck:02X}\r\n".encode()


def connect_ntrip(cfg):
    """Connect to NTRIP caster and return the socket."""
    ntrip = cfg["ntrip"]
    host = ntrip["host"]
    port = ntrip["port"]
    mount = ntrip["mountpoint"]
    user = ntrip["username"]
    password = ntrip["password"]

    sock = socket.socket()
    sock.settimeout(15)
    sock.connect((host, port))
    logger.info("Connected to NTRIP caster %s:%d", host, port)

    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = (
        f"GET /{mount} HTTP/1.0\r\n"
        f"User-Agent: NTRIP GCSRelay/1.0\r\n"
        f"Authorization: Basic {token}\r\n"
        "\r\n"
    )
    sock.sendall(req.encode())

    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += sock.recv(1)
    for line in resp.split(b"\r\n"):
        if line.startswith(b"ICY") or line.startswith(b"HTTP"):
            logger.info("NTRIP response: %s", line.decode().strip())
            break

    sock.settimeout(30)
    return sock


def gga_loop(sock, cfg):
    """Send GGA sentence to NTRIP caster every interval_sec."""
    gga_cfg = cfg["ntrip"]["gga"]
    lat = gga_cfg["lat"]
    lon = gga_cfg["lon"]
    alt = gga_cfg["alt"]
    interval = gga_cfg.get("interval_sec", 10)

    while _running:
        try:
            sock.sendall(make_gga(lat, lon, alt))
        except Exception:
            logger.warning("GGA send failed", exc_info=True)
            break
        time.sleep(interval)


def relay_server(listen_cfg):
    """Accept client connections and relay RTCM data to them."""
    host = listen_cfg.get("host", "0.0.0.0")
    port = listen_cfg["port"]

    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    server.settimeout(1.0)
    logger.info("Relay server listening on %s:%d", host, port)

    while _running:
        try:
            conn, addr = server.accept()
            logger.info("Client connected: %s:%d", addr[0], addr[1])
            with _clients_lock:
                _clients.append(conn)
        except socket.timeout:
            continue
        except Exception:
            if _running:
                logger.warning("Accept error", exc_info=True)
    server.close()


def forward_loop(ntrip_sock):
    """Read RTCM from NTRIP and broadcast to all connected clients."""
    total = 0
    while _running:
        try:
            data = ntrip_sock.recv(4096)
            if not data:
                logger.warning("NTRIP connection closed")
                break
            total += len(data)

            with _clients_lock:
                disconnected = []
                for s in _clients:
                    try:
                        s.sendall(data)
                    except Exception:
                        disconnected.append(s)
                for s in disconnected:
                    try:
                        s.close()
                    except Exception:
                        pass
                    if s in _clients:
                        _clients.remove(s)

            if total % 100_000 < 4096:
                with _clients_lock:
                    n = len(_clients)
                logger.info("RTCM: %s bytes relayed | %d client(s)", f"{total:,}", n)

        except socket.timeout:
            continue
        except Exception:
            logger.warning("Forward error", exc_info=True)
            break

    logger.info("Forward loop ended. Total: %s bytes", f"{total:,}")


def ntrip_reconnect_loop(cfg):
    """Keep reconnecting to NTRIP caster, then forward data."""
    retry_delay = 5
    while _running:
        ntrip_sock = None
        try:
            ntrip_sock = connect_ntrip(cfg)
            gga_thread = threading.Thread(
                target=gga_loop, args=(ntrip_sock, cfg), daemon=True
            )
            gga_thread.start()
            forward_loop(ntrip_sock)
        except Exception:
            logger.warning("NTRIP connection failed, retrying in %ds...", retry_delay,
                           exc_info=True)
        finally:
            if ntrip_sock:
                try:
                    ntrip_sock.close()
                except Exception:
                    pass

        if _running:
            time.sleep(retry_delay)


def main():
    parser = argparse.ArgumentParser(description="NTRIP Relay Server")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    cfg = load_config(args.config)
    logger.info("Config loaded from %s", args.config)

    def shutdown(signum, frame):
        global _running
        logger.info("Received signal %d, shutting down...", signum)
        _running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start relay server FIRST (always listening for Raspi)
    relay_thread = threading.Thread(
        target=relay_server, args=(cfg["relay"],), daemon=True
    )
    relay_thread.start()
    time.sleep(0.5)  # Give it a moment to bind

    logger.info("NTRIP relay running. Press Ctrl+C to stop.")

    # NTRIP connection with auto-reconnect
    ntrip_reconnect_loop(cfg)

    # Cleanup
    with _clients_lock:
        for s in _clients:
            try:
                s.close()
            except Exception:
                pass
        _clients.clear()
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
