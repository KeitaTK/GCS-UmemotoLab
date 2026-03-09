import logging
from .connection import MavlinkConnection

class GuidedControl:
    def __init__(self, connection: MavlinkConnection):
        self.connection = connection
        self.logger = logging.getLogger("GuidedControl")

    def set_position_target_local_ned(self, system_id: int, component_id: int, x: float, y: float, z: float, vx=0, vy=0, vz=0, yaw=0):
        self.logger.info(f"Sending SET_POSITION_TARGET_LOCAL_NED to system_id={system_id}, component_id={component_id}, x={x}, y={y}, z={z}, vx={vx}, vy={vy}, vz={vz}, yaw={yaw}")
        self.connection.send_set_position_target_local_ned(system_id, component_id, x, y, z, vx, vy, vz, yaw)
        print(f"[LOG] SET_POSITION_TARGET_LOCAL_NED sent: system_id={system_id}, component_id={component_id}, pos=({x},{y},{z}), vel=({vx},{vy},{vz}), yaw={yaw}")

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
