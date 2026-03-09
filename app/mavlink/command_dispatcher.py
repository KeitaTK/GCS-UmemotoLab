import logging
from .connection import MavlinkConnection

class CommandDispatcher:
    def __init__(self, connection: MavlinkConnection):
        self.connection = connection
        self.logger = logging.getLogger("CommandDispatcher")

    def arm(self, system_id: int, component_id: int):
        self.logger.info(f"Sending ARM command to system_id={system_id}, component_id={component_id}")
        self.connection.send_command_long(system_id, component_id, command=400, confirmation=0, param1=1)
        # レスポンス処理（必要なら）
        print(f"[LOG] ARM command sent: system_id={system_id}, component_id={component_id}")

    def disarm(self, system_id: int, component_id: int):
        self.logger.info(f"Sending DISARM command to system_id={system_id}, component_id={component_id}")
        self.connection.send_command_long(system_id, component_id, command=400, confirmation=0, param1=0)
        print(f"[LOG] DISARM command sent: system_id={system_id}, component_id={component_id}")

    def takeoff(self, system_id: int, component_id: int, altitude: float):
        self.logger.info(f"Sending TAKEOFF command to system_id={system_id}, component_id={component_id}, altitude={altitude}")
        self.connection.send_command_long(system_id, component_id, command=22, confirmation=0, param7=altitude)
        print(f"[LOG] TAKEOFF command sent: system_id={system_id}, component_id={component_id}, altitude={altitude}")

    def land(self, system_id: int, component_id: int):
        self.logger.info(f"Sending LAND command to system_id={system_id}, component_id={component_id}")
        self.connection.send_command_long(system_id, component_id, command=21, confirmation=0)
        print(f"[LOG] LAND command sent: system_id={system_id}, component_id={component_id}")
        response = self.connection.send_command_long(
            system_id,
            command=21   # MAV_CMD_NAV_LAND
        )
        self.handle_response(response)
        return response

    def handle_response(self, response):
        self.logger.info(f"Command response: {response}")
        if response is None:
            self.logger.warning("No response received.")
            print("[LOG] No response received.")
        elif isinstance(response, dict) and response.get("success"):
            self.logger.info("Command executed successfully.")
            print("[LOG] Command executed successfully.")
        else:
            self.logger.error(f"Command failed: {response}")
            print(f"[LOG] Command failed: {response}")
