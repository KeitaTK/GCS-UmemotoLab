import time
from pymavlink import mavutil

def main():
    print("Connecting to MAVLink UDP stream on port 14551 (Dedicated to Python script)...")
    try:
        master = mavutil.mavlink_connection('udpin:0.0.0.0:14551')
        print("Waiting for heartbeat...")
        
        while True:
            msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
            if msg:
                print(f"[{time.strftime('%H:%M:%S')}] Heartbeat received! System ID: {msg.get_srcSystem()}, Autopilot: {msg.autopilot}")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] No heartbeat received in the last 5 seconds. (Waiting for MAVProxy...)")
    except Exception as e:
        print("Error:", e)
        
if __name__ == '__main__':
    main()
