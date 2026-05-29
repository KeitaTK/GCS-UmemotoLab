# MessageRouter: 受信ループとディスパッチ
import threading
import logging
from .telemetry_store import TelemetryStore

class MessageRouter:
    def __init__(self, mavlink_conn, telemetry_store, command_dispatcher=None):
        self.logger = logging.getLogger(__name__)
        self.mavlink_conn = mavlink_conn
        self.telemetry_store = telemetry_store
        self.command_dispatcher = command_dispatcher
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.logger.info("MessageRouter受信ループ開始")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        self.logger.info("MessageRouter受信ループ停止")

    def _run(self):
        def callback(data, addr):
            # Parse MAVLink message
            try:
                self._parse_mavlink_message(data, addr)
            except Exception as e:
                self.logger.error(f"Error parsing MAVLink message: {e}")
        
        self.mavlink_conn.start(callback)
        
        # Periodically check for command timeouts
        while self.running:
            if self.command_dispatcher:
                try:
                    self.command_dispatcher.check_timeouts()
                except Exception as e:
                    self.logger.error(f"Error checking command timeouts: {e}")
            threading.Event().wait(0.5)  # Check timeouts every 500ms

    def _parse_mavlink_message(self, data, addr):
        """Parse incoming MAVLink message and route to appropriate handler."""
        try:
            from pymavlink import mavutil
            mav = mavutil.mavlink.MAVLink(None)
            
            # Attempt to unpack message
            msg = mav.parse_char_array(data)
            if not msg:
                return
            
            # Route message based on type
            msg_type = msg.get_type()
            system_id = msg.get_srcSystem()
            
            # Handle COMMAND_ACK
            if msg_type == 'COMMAND_ACK':
                self._handle_command_ack(system_id, msg)
            
            # Store telemetry data
            self.telemetry_store.update(system_id=system_id, message_type=msg_type, payload=msg)
            
        except Exception as e:
            self.logger.debug(f"MAVLink parse error: {e}")

    def _handle_command_ack(self, system_id: int, msg):
        """Handle COMMAND_ACK message."""
        if not self.command_dispatcher:
            return
        
        try:
            command_id = msg.command
            result = msg.result
            progress = getattr(msg, 'progress', 0)
            result_param2 = getattr(msg, 'result_param2', 0)
            
            self.command_dispatcher.handle_command_ack(
                system_id=system_id,
                command_id=command_id,
                result=result,
                progress=progress,
                result_param2=result_param2
            )
            self.logger.info(f"COMMAND_ACK processed: system_id={system_id}, cmd={command_id}, result={result}")
        except Exception as e:
            self.logger.error(f"Error handling COMMAND_ACK: {e}")
