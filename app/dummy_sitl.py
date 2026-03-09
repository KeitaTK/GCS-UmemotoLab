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
            if msg.get_type() == 'COMMAND_LONG':
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
    
    # Start listener thread
    threading.Thread(target=listen_commands, daemon=True).start()

    # Send heartbeat loop
    while True:
        master.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_QUADROTOR,
            mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
            mavutil.mavlink.MAV_MODE_GUIDED_ARMED,
            0,
            mavutil.mavlink.MAV_STATE_ACTIVE
        )
        time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys_id = int(sys.argv[1])
    else:
        sys_id = 1
    
    run_dummy_drone(sys_id, 14550)
