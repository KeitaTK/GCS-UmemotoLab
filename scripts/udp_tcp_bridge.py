"""MAVLink Bridge: GCS(UDP) <-> SSH Tunnel(TCP) <-> Raspi

Usage: python udp_tcp_bridge.py [bridge_udp_port] [tunnel_tcp_port]
  Default: bridge_udp_port=14552, tunnel_tcp_port=14551
  GCS listens on UDP 14550 and sends to bridge_udp_port.
"""
import socket, threading, sys

def main():
    bridge_udp_port = int(sys.argv[1]) if len(sys.argv) > 1 else 14552
    tunnel_tcp_port = int(sys.argv[2]) if len(sys.argv) > 2 else 14551

    # Listen for GCS outbound on UDP
    udp_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_in.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_in.bind(("127.0.0.1", bridge_udp_port))

    # Connect to SSH tunnel
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.connect(("127.0.0.1", tunnel_tcp_port))

    # For forwarding back to GCS
    udp_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"Bridge: UDP:{bridge_udp_port} <-> TCP:{tunnel_tcp_port} <-> Raspi", flush=True)
    
    def udp_to_tcp():
        while True:
            try:
                data, _ = udp_in.recvfrom(65535)
                if data:
                    tcp.sendall(data)
            except Exception as e:
                print(f"UDP->TCP: {e}", flush=True)
                break
    
    def tcp_to_udp():
        while True:
            try:
                data = tcp.recv(65535)
                if data:
                    udp_out.sendto(data, ("127.0.0.1", 14550))
            except Exception as e:
                print(f"TCP->UDP: {e}", flush=True)
                break
    
    threading.Thread(target=udp_to_tcp, daemon=True).start()
    threading.Thread(target=tcp_to_udp, daemon=True).start()
    
    try:
        while True:
            threading.Event().wait(10)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
