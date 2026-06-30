#!/usr/bin/env python3
"""Direct MAVLink Bridge: UDP <-> TCP via Tailscale (no SSH tunnel needed)

Usage: python scripts/direct_bridge.py [udp_port] [raspi_ip] [raspi_port]
  Default: udp_port=14552, raspi_ip=100.123.158.105, raspi_port=5760
"""
import socket
import threading
import sys

def main():
    udp_port = int(sys.argv[1]) if len(sys.argv) > 1 else 14552
    raspi_ip = sys.argv[2] if len(sys.argv) > 2 else '100.123.158.105'
    raspi_port = int(sys.argv[3]) if len(sys.argv) > 3 else 5760

    # UDP receive from GCS
    udp_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_in.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_in.bind(('127.0.0.1', udp_port))

    # TCP connect to Raspi via Tailscale
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.settimeout(15)
    tcp.connect((raspi_ip, raspi_port))

    # UDP for sending back to GCS
    udp_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f'Bridge: UDP:{udp_port} <-> TCP:{raspi_ip}:{raspi_port}', flush=True)

    def udp_to_tcp():
        while True:
            try:
                data, _ = udp_in.recvfrom(65535)
                if data:
                    tcp.sendall(data)
            except Exception:
                break

    def tcp_to_udp():
        while True:
            try:
                data = tcp.recv(65535)
                if data:
                    udp_out.sendto(data, ('127.0.0.1', 14550))
            except Exception:
                break

    threading.Thread(target=udp_to_tcp, daemon=True).start()
    threading.Thread(target=tcp_to_udp, daemon=True).start()

    try:
        while True:
            threading.Event().wait(10)
    except KeyboardInterrupt:
        print('\nBridge stopped', flush=True)

if __name__ == '__main__':
    main()
