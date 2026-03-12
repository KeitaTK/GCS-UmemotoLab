import time
from pymavlink import mavutil

def main():
    print("Connecting to MAVLink UDP stream on port 14550...")
    # NOTE: udpin is used because the local machine is receiving the UDP stream from the Raspi.
    
    try:
        master = mavutil.mavlink_connection('udpin:0.0.0.0:14550')
        print("Waiting for heartbeat...")
        
        while True:
            # Wait for a heartbeat
            msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
            if msg:
                print(f"[{time.strftime('%H:%M:%S')}] Heartbeat received! System ID: {msg.get_srcSystem()}")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] No heartbeat received in the last 5 seconds.")
                last_err = getattr(master, 'port_error', None)
                if last_err:
                   print("UDP Bind Error:", last_err)
                   break
    except KeyboardInterrupt:
        print("\nExiting.")
        
if __name__ == '__main__':
    main()
