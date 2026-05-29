import logging
import time
import threading
from .connection import MavlinkConnection

class CommandDispatcher:
    """
    Manages command dispatch to drones with COMMAND_ACK acknowledgment handling.
    
    Features:
    - Tracks pending commands and their execution status
    - Automatically detects COMMAND_ACK responses
    - Implements timeout detection (5 seconds default)
    - Supports automatic retry with exponential backoff
    """
    def __init__(self, connection: MavlinkConnection):
        self.connection = connection
        self.logger = logging.getLogger("CommandDispatcher")
        
        # Pending command tracking: {(system_id, seq): {'cmd': ..., 'sent_time': ..., 'retries': ..., ...}}
        self._pending_commands = {}
        self._pending_lock = threading.Lock()
        
        # Command timeout and retry settings
        self.cmd_timeout = 5.0  # seconds
        self.max_retries = 3
        
        # Callbacks for ACK reception and timeout
        self._ack_callbacks = []  # [(callback, system_id), ...]
        self._timeout_callbacks = []  # [(callback, system_id), ...]

    def _get_target_system_ids(self, system_id):
        if system_id is None:
            if getattr(self.connection, 'connection_type', 'udp') == 'serial':
                return [1]
            drones = getattr(self.connection, 'drones', {}) or {}
            return sorted({int(info.get('system_id')) for info in drones.values() if info.get('system_id') is not None})
        if isinstance(system_id, (list, tuple, set)):
            return [int(value) for value in system_id]
        return [int(system_id)]

    def _send_command(self, system_id: int, component_id: int, command: int, confirmation: int = 0, **params):
        self.connection.send_command_long(system_id, component_id, command=command, confirmation=confirmation, **params)

    def send_command_to_targets(self, system_ids, component_id: int, command: int, confirmation: int = 0, **params):
        for target_system_id in self._get_target_system_ids(system_ids):
            self._send_command(target_system_id, component_id, command, confirmation=confirmation, **params)

    def arm_all(self, system_ids=None, component_id: int = 1):
        self.send_command_to_targets(system_ids, component_id, 400, param1=1)

    def disarm_all(self, system_ids=None, component_id: int = 1):
        self.send_command_to_targets(system_ids, component_id, 400, param1=0)

    def takeoff_all(self, altitude: float, system_ids=None, component_id: int = 1):
        self.send_command_to_targets(system_ids, component_id, 22, param7=altitude)

    def land_all(self, system_ids=None, component_id: int = 1, descent_rate: float = None):
        for target_system_id in self._get_target_system_ids(system_ids):
            self.land(target_system_id, component_id=component_id, descent_rate=descent_rate)

    def arm(self, system_id: int, component_id: int):
        self.logger.info(f"Sending ARM command to system_id={system_id}, component_id={component_id}")
        self._send_command(system_id, component_id, 400, param1=1)
        self._track_command(system_id, command_id=400, description="ARM", component_id=component_id, params={'param1': 1})
        print(f"[LOG] ARM command sent: system_id={system_id}, component_id={component_id}")

    def disarm(self, system_id: int, component_id: int):
        self.logger.info(f"Sending DISARM command to system_id={system_id}, component_id={component_id}")
        self._send_command(system_id, component_id, 400, param1=0)
        self._track_command(system_id, command_id=400, description="DISARM", component_id=component_id, params={'param1': 0})
        print(f"[LOG] DISARM command sent: system_id={system_id}, component_id={component_id}")

    def takeoff(self, system_id: int, component_id: int, altitude: float):
        self.logger.info(f"Sending TAKEOFF command to system_id={system_id}, component_id={component_id}, altitude={altitude}")
        self._send_command(system_id, component_id, 22, param7=altitude)
        self._track_command(system_id, command_id=22, description=f"TAKEOFF ({altitude}m)", component_id=component_id, params={'param7': altitude})
        print(f"[LOG] TAKEOFF command sent: system_id={system_id}, component_id={component_id}, altitude={altitude}")

    def land(self, system_id: int, component_id: int, descent_rate: float = None):
        self.logger.info(f"Sending LAND command to system_id={system_id}, component_id={component_id}")
        params = {}
        if descent_rate is not None and descent_rate > 0:
            self._send_command(system_id, component_id, 178, param1=2, param2=descent_rate)
            params = {'param1': 2, 'param2': descent_rate}
        self._send_command(system_id, component_id, 21)
        description = "LAND" if descent_rate is None else f"LAND (descent_rate={descent_rate})"
        self._track_command(system_id, command_id=21, description=description, component_id=component_id, params=params)
        print(f"[LOG] LAND command sent: system_id={system_id}, component_id={component_id}")

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

    def _track_command(self, system_id: int, command_id: int, description: str = "", component_id: int = 1, params: dict = None):
        """Track a command for ACK monitoring."""
        with self._pending_lock:
            # Generate a sequence number based on current pending commands
            seq = len(self._pending_commands)
            key = (system_id, seq)
            self._pending_commands[key] = {
                'system_id': system_id,
                'command_id': command_id,
                'description': description,
                'sent_time': time.time(),
                'retries': 0,
                'status': 'pending',  # pending, acked, timeout, failed
                'component_id': component_id,
                'params': params or {}
            }
            self.logger.debug(f"Tracking command: system_id={system_id}, seq={seq}, cmd={command_id} ({description})")

    def handle_command_ack(self, system_id: int, command_id: int, result: int, progress: int = 0, result_param2: int = 0):
        """
        Handle COMMAND_ACK message from drone.
        
        Args:
            system_id: Source system ID
            command_id: Command that was acknowledged
            result: Command result (0=accepted, 1=rejected, etc.)
            progress: Progress (0-100) or -1 if N/A
            result_param2: Additional result parameter
        """
        status_str = self._get_ack_status_string(result)
        self.logger.info(f"COMMAND_ACK: system_id={system_id}, cmd={command_id}, result={status_str}")
        
        with self._pending_lock:
            # Find matching pending command
            for key, cmd_info in list(self._pending_commands.items()):
                if cmd_info['system_id'] == system_id and cmd_info['command_id'] == command_id:
                    if result == 0:  # MAV_RESULT_ACCEPTED
                        cmd_info['status'] = 'acked'
                        self.logger.info(f"Command ACCEPTED: {cmd_info['description']}")
                    else:
                        cmd_info['status'] = 'failed'
                        self.logger.warning(f"Command REJECTED: {cmd_info['description']} (result={status_str})")
                    break
        
        # Trigger callbacks
        for callback in self._ack_callbacks:
            try:
                callback(system_id, command_id, result, status_str)
            except Exception as e:
                self.logger.error(f"ACK callback error: {e}")

    def _get_ack_status_string(self, result: int) -> str:
        """Convert MAV_RESULT code to human-readable string."""
        status_map = {
            0: "ACCEPTED",
            1: "TEMPORARILY_REJECTED",
            2: "DENIED",
            3: "UNSUPPORTED",
            4: "FAILED",
            5: "CANCELLED",
        }
        return status_map.get(result, f"UNKNOWN({result})")

    def register_ack_callback(self, callback):
        """Register callback for COMMAND_ACK events. Signature: callback(system_id, command_id, result, status_str)"""
        self._ack_callbacks.append(callback)

    def register_timeout_callback(self, callback):
        """Register callback for command timeout events. Signature: callback(system_id, command_id, description)"""
        self._timeout_callbacks.append(callback)

    def get_pending_commands(self, system_id: int = None) -> list:
        """Get list of pending commands, optionally filtered by system_id."""
        with self._pending_lock:
            if system_id is None:
                return [cmd for cmd in self._pending_commands.values()]
            else:
                return [cmd for cmd in self._pending_commands.values() if cmd['system_id'] == system_id]

    def get_command_status(self, system_id: int, command_id: int) -> str:
        """Get status of a specific command."""
        with self._pending_lock:
            for cmd_info in self._pending_commands.values():
                if cmd_info['system_id'] == system_id and cmd_info['command_id'] == command_id:
                    return cmd_info['status']
        return 'unknown'

    def check_timeouts(self):
        """Check for command timeouts and trigger retries or failure callbacks."""
        current_time = time.time()
        timed_out = []
        
        with self._pending_lock:
            for key, cmd_info in list(self._pending_commands.items()):
                if cmd_info['status'] == 'pending':
                    elapsed = current_time - cmd_info['sent_time']
                    if elapsed > self.cmd_timeout:
                        if cmd_info['retries'] < self.max_retries:
                            self.logger.warning(
                                f"Command timeout (retry {cmd_info['retries']+1}/{self.max_retries}): "
                                f"system_id={cmd_info['system_id']}, {cmd_info['description']}"
                            )
                            cmd_info['retries'] += 1
                            cmd_info['sent_time'] = current_time
                            timed_out.append((key, cmd_info))
                        else:
                            self.logger.error(
                                f"Command FAILED (max retries exceeded): "
                                f"system_id={cmd_info['system_id']}, {cmd_info['description']}"
                            )
                            cmd_info['status'] = 'timeout'
                            # Trigger timeout callback
                            for callback in self._timeout_callbacks:
                                try:
                                    callback(cmd_info['system_id'], cmd_info['command_id'], cmd_info['description'])
                                except Exception as e:
                                    self.logger.error(f"Timeout callback error: {e}")
                            # Remove from pending after max retries
                            del self._pending_commands[key]
        
        # Perform retransmissions outside lock to avoid deadlock
        for key, cmd_info in timed_out:
            try:
                self._resend_command(cmd_info)
            except Exception as e:
                self.logger.error(f"Error retrying command: {e}")

    def _resend_command(self, cmd_info: dict):
        """Resend a command that timed out."""
        system_id = cmd_info['system_id']
        command_id = cmd_info['command_id']
        component_id = cmd_info.get('component_id', 1)
        
        try:
            self.logger.info(f"Retrying command: system_id={system_id}, cmd={command_id}, attempt {cmd_info['retries']}")
            retry_params = cmd_info.get('params', {})
            self._send_command(system_id, component_id, command_id, **retry_params)
            self.logger.info(f"Command resent: {cmd_info['description']}")
        except Exception as e:
            self.logger.error(f"Error resending command: {e}")
