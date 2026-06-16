import logging
from mavlink.connection import MavlinkConnection

class GuidedControl:
    def __init__(self, connection: MavlinkConnection):
        self.connection = connection
        self.logger = logging.getLogger("GuidedControl")

    def set_position_target_local_ned(self, system_id: int, component_id: int, x: float, y: float, z: float, vx=0, vy=0, vz=0, yaw=0):
        self.logger.info(f"Sending SET_POSITION_TARGET_LOCAL_NED to system_id={system_id}, component_id={component_id}, x={x}, y={y}, z={z}, vx={vx}, vy={vy}, vz={vz}, yaw={yaw}")
        self.connection.send_set_position_target_local_ned(system_id, component_id, x, y, z, vx, vy, vz, yaw)
        print(f"[LOG] SET_POSITION_TARGET_LOCAL_NED sent: system_id={system_id}, component_id={component_id}, pos=({x},{y},{z}), vel=({vx},{vy},{vz}), yaw={yaw}")

    def set_velocity_target_local_ned(self, system_id: int, component_id: int, vx: float, vy: float, vz: float, yaw=0):
        self.logger.info(f"Sending velocity target to system_id={system_id}, component_id={component_id}, vx={vx}, vy={vy}, vz={vz}, yaw={yaw}")
        self.connection.send_set_position_target_local_ned(system_id, component_id, 0, 0, 0, vx, vy, vz, yaw=yaw, type_mask=0b0000110111000111)
        print(f"[LOG] Velocity target sent: system_id={system_id}, component_id={component_id}, vel=({vx},{vy},{vz}), yaw={yaw}")

    def indoor_takeoff(self, system_id: int, component_id: int, throttle_pct: float = 65):
        """Indoor takeoff via RC_CHANNELS_OVERRIDE throttle (STABILIZE mode).
        
        Sends centered roll/pitch/yaw with throttle at throttle_pct%.
        Drone will climb. Send indoor_land() or disarm to stop.
        """
        throttle_raw = int(1100 + (throttle_pct / 100.0) * 800)  # 1100-1900
        self.connection.send_rc_channels_override(
            system_id, chan3_raw=throttle_raw,
            chan1_raw=1500, chan2_raw=1500, chan4_raw=1500
        )
        self.logger.info(f"Indoor takeoff: throttle={throttle_pct}% ({throttle_raw})")
        print(f"[Indoor] Takeoff: throttle {throttle_pct}%")

    def indoor_land(self, system_id: int, component_id: int):
        """Indoor landing via RC_CHANNELS_OVERRIDE throttle min (STABILIZE mode).
        
        Sets throttle to minimum (1100). Drone will descend. Disarm after landing.
        """
        self.connection.send_rc_channels_override(
            system_id, chan3_raw=1100,
            chan1_raw=1500, chan2_raw=1500, chan4_raw=1500
        )
        self.logger.info(f"Indoor land: throttle=min")
        print(f"[Indoor] Land: throttle min")

    def handle_response(self, response):
        self.logger.info(f"GuidedControl response: {response}")
        if response is None:
            self.logger.warning("No response received.")
            print("[LOG] No response received.")
        elif isinstance(response, dict) and response.get("success"):
            self.logger.info("GuidedControl command executed successfully.")
            print("[LOG] GuidedControl command executed successfully.")
        else:
            self.logger.error(f"GuidedControl command failed: {response}")
            print(f"[LOG] GuidedControl command failed: {response}")
