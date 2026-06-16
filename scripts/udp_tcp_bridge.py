"""MAVLink Bridge: GCS(UDP) <-> SSH Tunnel(TCP) <-> Raspi"""
import socket, threading, sys

def main():
    # Listen for GCS outbound on UDP 14552
    udp_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_in.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_in.bind(("127.0.0.1", 14552))
    
    # Connect to SSH tunnel
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.connect(("127.0.0.1", 14551))
    
    # For forwarding back to GCS
    udp_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print("Bridge: UDP:14552 <-> TCP:14551 <-> Raspi", flush=True)
    
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
