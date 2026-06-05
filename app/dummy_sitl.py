import time
import sys
import threading
import socket
import struct
from pymavlink import mavutil

def run_dummy_drone(system_id: int, port: int):
    # Create an outgoing UDP connection with explicit MAVLink setup
    try:
        master = mavutil.mavlink_connection(f'udpout:127.0.0.1:{port}', source_system=system_id, baud=115200)
        print(f"Dummy Drone {system_id} started, sending MAVLink to 127.0.0.1:{port}", flush=True)
    except Exception as e:
        print(f"Error creating connection for drone {system_id}: {e}", flush=True)
        return
    
    def listen_commands():
        """Listen for incoming commands (non-blocking)"""
        master.port.settimeout(0.1)  # Non-blocking
        while True:
            try:
                msg = master.recv_match(blocking=False)
                if not msg:
                    time.sleep(0.01)
                    continue
                    
                msg_type = msg.get_type()
                print(f"[Drone {system_id}] Received {msg_type}", flush=True)
                
                if msg_type == 'COMMAND_LONG':
                    print(f"[Drone {system_id}] Command: {msg.command}", flush=True)
                    # Send ACK
                    master.mav.command_ack_send(
                        msg.command,
                        0,  # MAV_RESULT_ACCEPTED
                        progress=0,
                        result_param2=0,
                        target_system=msg.sysid,
                        target_component=msg.compid
                    )
                elif msg_type == 'GPS_RTCM_DATA':
                    print(f"[Drone {system_id}] Received RTCM data, length: {len(msg.data)}", flush=True)
            except socket.timeout:
                pass
            except Exception as e:
                print(f"[Drone {system_id}] Listener error: {e}", flush=True)
                time.sleep(0.01)
    
    # Start listener thread
    threading.Thread(target=listen_commands, daemon=True).start()

    # Send heartbeat and telemetry loop
    sequence = 0
    while True:
        try:
            # Send heartbeat with all required parameters
            master.mav.heartbeat_send(
                type=mavutil.mavlink.MAV_TYPE_QUADROTOR,
                autopilot=mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                base_mode=mavutil.mavlink.MAV_MODE_GUIDED_ARMED,
                custom_mode=0,
                system_status=mavutil.mavlink.MAV_STATE_ACTIVE,
                mavlink_version=3
            )
            
            # Send attitude
            master.mav.attitude_send(
                time_boot_ms=int(time.time() * 1000) % 1000000,
                roll=0.0,
                pitch=0.0,
                yaw=0.0,
                rollspeed=0.0,
                pitchspeed=0.0,
                yawspeed=0.0
            )
            
            sequence += 1
            time.sleep(1)
            
        except Exception as e:
            print(f"[Drone {system_id}] Send error: {e}", flush=True)
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
