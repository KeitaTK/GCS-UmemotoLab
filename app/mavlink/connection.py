# MavlinkConnection: UDP/Serial入出力用
import socket
import threading
import logging
import yaml
import serial
import os
import time

class MavlinkConnection:
    """
    Manages MAVLink communication over UDP or Serial with enhanced error handling.
    
    Features:
    - Packet loss detection and reporting
    - Automatic serial connection recovery
    - Connection state tracking
    - Error event callbacks
    """
    def __init__(self, config_path):
        from pymavlink import mavutil
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)
        
        # Connection type (UDP or Serial)
        self.connection_type = self.config.get('connection_type', 'udp')
        
        # Connection state and error tracking
        self.is_connected = False
        self.connection_error = None
        self.packet_loss_count = 0
        self.packet_received_count = 0
        self.error_callbacks = []  # Callbacks for connection errors
        
        if self.connection_type == 'serial':
            # Serial connection for Pixhawk
            self.serial_port = self.config.get('serial_port', '/dev/ttyACM0')
            self.serial_baudrate = self.config.get('serial_baudrate', 115200)
            self.serial_conn = None
            self.serial_error_count = 0
            self.serial_max_errors = 5  # Consecutive errors before critical
            self.logger.info(f"Serial mode: {self.serial_port} @ {self.serial_baudrate} baud")
        else:
            # UDP connection (default)
            self.udp_port = self.config.get('udp_listen_port', 14550)
            self.drones = self.config.get('drones', {})
            # Dedicated receive socket — never used for sendto()
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", self.udp_port))
            self.sock.settimeout(5.0)  # Timeout to detect UDP connection loss
            # Dedicated send socket — keeps sendto() from interfering with
            # recvfrom() on Windows (where sharing a UDP socket for both can
            # cause recvfrom to drop when sendto is called frequently, e.g.
            # during RTCM GPS_RTCM_DATA injection).
            self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_timeout_count = 0
            self.logger.info(f"UDP mode: listening on 0.0.0.0:{self.udp_port}")
        
        # MAVLink encode/decode object using a bytearray buffer
        self.mav = mavutil.mavlink.MAVLink(bytearray())
        
        self.running = False
        self.recv_thread = None
        self.recv_callback = None

    def _load_config(self, config_or_path):
        """Load config from a YAML file path or use a dict directly."""
        if isinstance(config_or_path, dict):
            return config_or_path
        with open(config_or_path, 'r') as f:
            return yaml.safe_load(f)

    def register_error_callback(self, callback):
        """Register callback for connection errors. Signature: callback(error_type, message)"""
        self.error_callbacks.append(callback)

    def get_connection_status(self) -> dict:
        """Get current connection status and statistics"""
        return {
            'is_connected': self.is_connected,
            'connection_type': self.connection_type,
            'packet_received': self.packet_received_count,
            'packet_loss': self.packet_loss_count,
            'last_error': self.connection_error,
        }

    def _trigger_error_callback(self, error_type: str, message: str):
        """Trigger all registered error callbacks"""
        self.connection_error = message
        for callback in self.error_callbacks:
            try:
                callback(error_type, message)
            except Exception as e:
                self.logger.error(f"Error callback error: {e}")


    def start(self, recv_callback):
        self.running = True
        self.recv_callback = recv_callback
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()
        
        if self.connection_type == 'serial':
            self.logger.info(f"Serial受信を開始: {self.serial_port}")
        else:
            self.logger.info(f"UDP受信を開始: 0.0.0.0:{self.udp_port}")

    def stop(self):
        self.running = False
        if self.recv_thread:
            self.recv_thread.join()
        
        if self.connection_type == 'serial':
            if self.serial_conn:
                self.serial_conn.close()
            self.logger.info("Serial受信を停止")
        else:
            self.sock.close()
            self._send_sock.close()
            self.logger.info("UDP受信を停止")

    def _recv_loop(self):
        if self.connection_type == 'serial':
            self._recv_loop_serial()
        else:
            self._recv_loop_udp()
    
    def _recv_loop_serial(self):
        """Receive MAVLink data from serial port (Pixhawk) with error recovery"""
        consecutive_errors = 0
        last_connection_attempt = 0
        reconnect_delay = 1.0  # Initial delay before reconnect
        
        while self.running:
            try:
                # Check if connection is open, attempt to open if not
                if not self.serial_conn or not self.serial_conn.is_open:
                    # Implement exponential backoff for reconnection attempts
                    current_time = time.time()
                    if current_time - last_connection_attempt < reconnect_delay:
                        threading.Event().wait(0.1)
                        continue
                    
                    last_connection_attempt = current_time
                    try:
                        self.serial_conn = serial.Serial(
                            self.serial_port,
                            self.serial_baudrate,
                            timeout=1
                        )
                        self.is_connected = True
                        self.serial_error_count = 0
                        consecutive_errors = 0
                        reconnect_delay = 1.0  # Reset delay on successful connection
                        self.logger.info(f"Serial port opened: {self.serial_port}")
                    except serial.SerialException as e:
                        self.is_connected = False
                        self.logger.warning(f"Failed to open serial port: {e}")
                        self._trigger_error_callback('SERIAL_OPEN_FAILED', str(e))
                        continue
                
                # Read data if available
                if self.serial_conn.in_waiting > 0:
                    try:
                        data = self.serial_conn.read(self.serial_conn.in_waiting)
                        if data and self.recv_callback:
                            self.recv_callback(data, (self.serial_port, 0))
                            self.packet_received_count += 1
                            consecutive_errors = 0  # Reset error counter on success
                    except Exception as e:
                        self.logger.debug(f"Error reading serial data: {e}")
                        consecutive_errors += 1
                else:
                    threading.Event().wait(0.01)
                    
            except serial.SerialException as e:
                consecutive_errors += 1
                self.serial_error_count += 1
                self.logger.warning(f"Serial接続エラー (count={self.serial_error_count}): {e}")
                
                if self.serial_error_count >= self.serial_max_errors:
                    self.is_connected = False
                    self._trigger_error_callback('SERIAL_CRITICAL', f"Serial connection failed {self.serial_error_count} times")
                
                if self.serial_conn:
                    try:
                        self.serial_conn.close()
                    except:
                        pass
                self.serial_conn = None
                
                # Exponential backoff: increase delay with each error
                reconnect_delay = min(reconnect_delay * 1.5, 5.0)  # Cap at 5 seconds
                threading.Event().wait(min(0.5, reconnect_delay))
                
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(f"Unexpected serial error: {e}")
                threading.Event().wait(0.05)

    
    def _recv_loop_udp(self):
        """Receive MAVLink data from UDP port with packet loss detection"""
        timeout_count = 0
        max_consecutive_timeouts = 30  # Increased threshold for local dev (was 10)
        
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                if self.recv_callback:
                    self.recv_callback(data, addr)
                    self.packet_received_count += 1
                    timeout_count = 0  # Reset timeout counter on successful receive
                    self.is_connected = True
                    
            except socket.timeout:
                timeout_count += 1
                if timeout_count >= max_consecutive_timeouts:
                    self.is_connected = False
                    self.packet_loss_count += 1
                    msg = f"UDP receive timeout detected (count={self.packet_loss_count})"
                    self.logger.warning(msg)
                    self._trigger_error_callback('UDP_TIMEOUT', msg)
                    timeout_count = 0  # Reset for next cycle
                    
            except ConnectionResetError as e:
                self.is_connected = False
                self.packet_loss_count += 1
                msg = f"UDP connection reset: {e}"
                self.logger.warning(msg)
                self._trigger_error_callback('UDP_CONNECTION_RESET', msg)
                threading.Event().wait(0.5)
                
            except OSError as e:
                self.is_connected = False
                self.packet_loss_count += 1
                msg = f"UDP socket error (errno={e.errno}): {e}"
                self.logger.error(msg)
                self._trigger_error_callback('UDP_SOCKET_ERROR', msg)
                # If socket is closed (e.g., EBADF), break out
                if e.errno == 9:  # EBADF - bad file descriptor
                    self.logger.error("UDP socket closed, stopping receive loop")
                    break
                threading.Event().wait(0.5)
                
            except Exception as e:
                self.logger.error(f"UDP受信エラー: {e}", exc_info=True)
                self.is_connected = False
                self._trigger_error_callback('UDP_ERROR', str(e))
                threading.Event().wait(0.1)


    def send(self, system_id, data):
        """Send MAVLink data to the appropriate destination.
        
        Returns:
            bool: True if data was sent successfully, False otherwise.
        """
        # ── DEBUG: log every sent frame ──────────────────────────────────
        if isinstance(data, (bytes, bytearray)) and len(data) > 0:
            magic = data[0]
            magic_hex = f"0x{magic:02X}"
            magic_name = "v2(0xFD)" if magic == 0xFD else ("v1(0xFE)" if magic == 0xFE else "UNKNOWN")
            first_bytes = data[:16].hex(' ') if len(data) > 16 else data.hex(' ')
            msgid = data[5] if len(data) > 5 else None
            self.logger.info(
                f"[SEND] system_id={system_id}, len={len(data)}, magic={magic_hex} ({magic_name}), "
                f"msgid={msgid}, first_bytes=[{first_bytes}]"
            )
        # ─────────────────────────────────────────────────────────────────

        if self.connection_type == 'serial':
            # For serial mode, send back to Pixhawk
            if not self.serial_conn or not self.serial_conn.is_open:
                self.logger.error(
                    f"Serial送信失敗: シリアルポートが開いていません (system_id={system_id}, "
                    f"port={self.serial_port}). Pixhawkが接続されているか確認してください。"
                )
                self._trigger_error_callback(
                    'SERIAL_SEND_FAILED',
                    f'Serial port {self.serial_port} is not open. Is Pixhawk connected?'
                )
                return False
            try:
                self.serial_conn.write(data)
                self.logger.debug(f"Serial送信: {len(data)} bytes")
                return True
            except Exception as e:
                self.logger.error(f"Serial送信エラー: {e}")
                self._trigger_error_callback('SERIAL_SEND_ERROR', str(e))
                return False
        else:
            # UDP mode: send to configured endpoint
            sent = False
            for drone_name, drone_info in self.drones.items():
                if drone_info.get('system_id') == system_id:
                    endpoint = drone_info.get('endpoint')
                    if endpoint:
                        ip, port = endpoint.split(":")
                        self._send_sock.sendto(data, (ip, int(port)))
                        self.logger.debug(f"送信: {ip}:{port} (system_id={system_id})")
                        sent = True
                    break
            if not sent:
                self.logger.error(
                    f"UDP送信失敗: system_id={system_id} に一致するドローンが設定ファイルにありません。"
                    f" 設定済みドローン: {list(self.drones.keys())}"
                )
            return sent

    def send_to_system(self, system_id, data):
        """
        Send MAVLink data to a specific system.
        Alias for send() for clarity.
        """
        self.send(system_id, data)

    def _send_encoded_frame(self, system_id, frame: bytes):
        self.send(system_id, frame)

    def send_rc_channels_override(self, system_id, chan1_raw=1500, chan2_raw=1500,
                                    chan3_raw=1100, chan4_raw=1500,
                                    chan5_raw=0, chan6_raw=0, chan7_raw=0, chan8_raw=0):
        """Send RC_CHANNELS_OVERRIDE (msgid=70) to simulate RC input.
        
        Channel values: 1000-2000 (PWM), 0=ignore, UINT16_MAX=release.
        Defaults set all to center except throttle at minimum.
        
        Uses pymavlink encode+pack to ensure CRC_EXTRA is included in CRC.
        """
        msg = self.mav.rc_channels_override_encode(
            0,  # target_system (0=all)
            0,  # target_component (0=all)
            int(chan1_raw), int(chan2_raw), int(chan3_raw), int(chan4_raw),
            int(chan5_raw), int(chan6_raw), int(chan7_raw), int(chan8_raw),
            0, 0, 0, 0, 0, 0, 0, 0,  # chan9-16 = 0
            0, 0,  # chan17-18 = 0
        )
        frame = msg.pack(self.mav)
        self.send(system_id, frame)
        self.logger.debug(
            f"RC_CHANNELS_OVERRIDE sent: system_id={system_id}, "
            f"ch1={chan1_raw}, ch2={chan2_raw}, ch3={chan3_raw}, ch4={chan4_raw}"
        )

    def send_command_long(self, system_id, component_id, command, confirmation=0, **params):
        """Send COMMAND_LONG using pymavlink's standard encoder (correct CRC)."""
        msg = self.mav.command_long_encode(
            target_system=system_id,
            target_component=component_id,
            command=command,
            confirmation=confirmation,
            param1=float(params.get('param1', 0.0)),
            param2=float(params.get('param2', 0.0)),
            param3=float(params.get('param3', 0.0)),
            param4=float(params.get('param4', 0.0)),
            param5=float(params.get('param5', 0.0)),
            param6=float(params.get('param6', 0.0)),
            param7=float(params.get('param7', 0.0)),
        )
        frame = msg.pack(self.mav)
        self._send_encoded_frame(system_id, frame)
        self.logger.debug(
            f"COMMAND_LONG sent: system_id={system_id}, component_id={component_id}, command={command}, params=[{params}], confirmation={confirmation}"
        )

    def send_set_position_target_local_ned(self, system_id, component_id, x, y, z, vx=0, vy=0, vz=0, yaw=0, yaw_rate=0, coordinate_frame=1, type_mask=None):
        """Send SET_POSITION_TARGET_LOCAL_NED using pymavlink encode+pack (CRC_EXTRA included)."""
        if type_mask is None:
            # Use position targets by default and ignore velocity/acceleration/yaw-rate fields.
            type_mask = 0b0000111111000111

        msg = self.mav.set_position_target_local_ned_encode(
            int(time.time() * 1000) & 0xFFFFFFFF,  # time_boot_ms
            int(system_id),
            int(component_id),
            int(coordinate_frame),
            int(type_mask),
            float(x), float(y), float(z),
            float(vx), float(vy), float(vz),
            0.0, 0.0, 0.0,  # afx, afy, afz
            float(yaw),
            float(yaw_rate),
        )
        frame = msg.pack(self.mav)
        self._send_encoded_frame(system_id, frame)
        self.logger.debug(
            f"SET_POSITION_TARGET_LOCAL_NED sent: system_id={system_id}, component_id={component_id}, pos=({x},{y},{z}), vel=({vx},{vy},{vz}), yaw={yaw}, yaw_rate={yaw_rate}"
        )
