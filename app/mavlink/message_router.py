# MessageRouter: 受信ループとディスパッチ
import threading
import logging
from pymavlink import mavutil
from rtk_tools.telemetry_store import TelemetryStore

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
        self.mav = mavutil.mavlink.MAVLink(None)

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

            mav = mavutil.mavlink.MAVLink(None)
            
            # Attempt to unpack message using correct API
            msgs = None
            try:
                # Try newer API first (parse_buffer for bytes)
                msgs = self.mav.parse_buffer(data)
            except (AttributeError, TypeError):
                try:
                    # Fallback to parse_char_array
                    msgs = mav.parse_char_array(data)
                except (AttributeError, TypeError):
                    # Last resort: try unpacking with struct
                    if len(data) < 8:
                        return
                    # Parse as raw MAVLink 1.0 frame
                    try:
                        msgs = mav.decode(data)
                    except:
                        return
            
            if not msgs:
                return
            
            # Handle both single message and list of messages
            if not isinstance(msgs, list):
                msgs = [msgs]
            
            for msg in msgs:
                if not msg:
                    continue
                
                # Route message based on type
                msg_type = msg.get_type()
                system_id = msg.get_srcSystem()
                
                # Enhanced logging for GPS_RAW_INT with fix_type
                if msg_type == 'GPS_RAW_INT':
                    fix_type = getattr(msg, 'fix_type', -1)
                    fix_name = self._gps_fix_type_name(fix_type)
                    num_sats = getattr(msg, 'satellites_visible', 0)
                    lat = getattr(msg, 'lat', 0) / 1e7
                    lon = getattr(msg, 'lon', 0) / 1e7
                    alt = getattr(msg, 'alt', 0) / 1000.0
                    hdop = getattr(msg, 'eph', 0) / 100.0  # HDOP in cm -> m
                    self.logger.info(
                        f"GPS_RAW from sys={system_id}: fix={fix_type}({fix_name}), "
                        f"sats={num_sats}, lat={lat:.6f}, lon={lon:.6f}, "
                        f"alt={alt:.2f}m, hdop={hdop:.2f}"
                    )
                else:
                    self.logger.debug(f"Received {msg_type} from system {system_id}")
                
                # Handle COMMAND_ACK
                if msg_type == 'COMMAND_ACK':
                    self._handle_command_ack(system_id, msg)

                # Handle STATUSTEXT -> ring buffer in telemetry store
                if msg_type == 'STATUSTEXT':
                    self._handle_status_text(system_id, msg)

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

    def _handle_status_text(self, system_id: int, msg):
        """Handle STATUSTEXT message: push to ring buffer in telemetry store."""
        try:
            text = getattr(msg, 'text', '')
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='ignore').rstrip('\x00')
            text = str(text)
            severity = getattr(msg, 'severity', 7)  # default DEBUG
            name = getattr(msg, 'name', '')
            if isinstance(name, bytes):
                name = name.decode('utf-8', errors='ignore').rstrip('\x00')
            name = str(name)

            self.telemetry_store.add_status_text(system_id, text, severity, name)
            self.logger.debug(
                f"STATUSTEXT from sys={system_id}: sev={severity}, text={text!r}"
            )
        except Exception as e:
            self.logger.error(f"Error handling STATUSTEXT: {e}")

    @staticmethod
    def _gps_fix_type_name(fix_type: int) -> str:
        """Convert MAVLink GPS_FIX_TYPE to human-readable string."""
        fix_names = {
            0: "NO_GPS",
            1: "NO_FIX",
            2: "2D_FIX",
            3: "3D_FIX",
            4: "DGPS",
            5: "RTK_FLOAT",
            6: "RTK_FIXED",
            7: "STATIC",
            8: "PPP",
        }
        return fix_names.get(fix_type, f"UNKNOWN({fix_type})")

