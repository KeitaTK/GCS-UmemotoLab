import time
from pymavlink import mavutil

def main():
    # Attempt to bind without conflicting if QGC is not running on 0.0.0.0
    print("Binding to udp:192.168.11.6:14550...")
    try:
        # Binding specifically to the local IP address
        master = mavutil.mavlink_connection('udpin:192.168.11.6:14550')
        print("Waiting for heartbeat...")
        
        while True:
            msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
            if msg:
                print(f"[{time.strftime('%H:%M:%S')}] Heartbeat received! System ID: {msg.get_srcSystem()}")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] No heartbeat received in the last 5 seconds. (QGC may be holding the port exclusive)")
    except Exception as e:
        print("Error:", e)
        print("If you get Address already in use, QGC is exclusively binding to 14550 and you need to close QGC or route via TCP.")
        
if __name__ == '__main__':
    main()
