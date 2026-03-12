import time
from pymavlink import mavutil

def main():
    print("Connecting to MAVLink UDP stream on port 14550 using udpin:localhost:14550 ...")
    try:
        # Binding to localhost explicitly allows parallel receive sometimes if another process binds generically
        # However, typically only one program can bind the same UDP port.
        # Alternatively, we can let MAVProxy broadcast so multiple GCS can connect. 
        master = mavutil.mavlink_connection('udpin:127.0.0.1:14550')
        print("Waiting for heartbeat...")
        
        while True:
            msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
            if msg:
                print(f"[{time.strftime('%H:%M:%S')}] Heartbeat received! System ID: {msg.get_srcSystem()}")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] No heartbeat received in the last 5 seconds. (Is another app like QGC holding the port?)")
    except KeyboardInterrupt:
        print("\nExiting.")
        
if __name__ == '__main__':
    main()
