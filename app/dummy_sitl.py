import time
import sys
import threading
from pymavlink import mavutil

def run_dummy_drone(system_id: int, port: int):
    # Create an outgoing UDP connection
    master = mavutil.mavlink_connection(f'udpout:127.0.0.1:{port}', source_system=system_id)
    print(f"Dummy Drone {system_id} started, sending MAVLink to 127.0.0.1:{port}")
    
    def listen_commands():
        while True:
            msg = master.recv_match(blocking=True)
            if not msg:
                continue
            msg_type = msg.get_type()
            
            if msg_type == 'COMMAND_LONG':
                print(f"[Drone {system_id}] Received command: {msg.command}")
                # Send ack
                master.mav.command_ack_send(
                    msg.command,
                    0,  # MAV_RESULT_ACCEPTED
                    progress=0,
                    result_param2=0,
                    target_system=msg.sysid,
                    target_component=msg.compid
                )
            elif msg_type == 'GPS_RTCM_DATA':
                print(f"[Drone {system_id}] Received RTCM data, length: {len(msg.data)}")
    
    # Start listener thread
    threading.Thread(target=listen_commands, daemon=True).start()

    # Send heartbeat and telemetry loop
    while True:
        master.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_QUADROTOR,
            mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
            mavutil.mavlink.MAV_MODE_GUIDED_ARMED,
            0,
            mavutil.mavlink.MAV_STATE_ACTIVE
        )
        
        # Send fake sys_status
        master.mav.sys_status_send(
            0, 0, 0, 0, 12500, -1, -1, 0, 0, 0, 0, 0, 0, 0
        )
        
        # Send fake named_value_float for debug graph
        master.mav.named_value_float_send(
            time.ticks_ms() if hasattr(time, 'ticks_ms') else int(time.time() * 1000) % 10000,
            b"test_val",
            1.23 + (system_id * 0.1)
        )
        
        time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys_ids = [int(x) for x in sys.argv[1].split(',')]
    else:
        sys_ids = [1]
        
    for sid in sys_ids:
        threading.Thread(target=run_dummy_drone, args=(sid, 14550), daemon=True).start()
        
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down dummy drones.")
