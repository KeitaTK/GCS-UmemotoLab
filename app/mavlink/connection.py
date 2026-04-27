# MavlinkConnection: UDP/Serial入出力用
import socket
import threading
import logging
import yaml
import serial
import os

class MavlinkConnection:
    def __init__(self, config_path):
        from pymavlink import mavutil
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)
        
        # Connection type (UDP or Serial)
        self.connection_type = self.config.get('connection_type', 'udp')
        
        if self.connection_type == 'serial':
            # Serial connection for Pixhawk
            self.serial_port = self.config.get('serial_port', '/dev/ttyACM0')
            self.serial_baudrate = self.config.get('serial_baudrate', 115200)
            self.serial_conn = None
            self.logger.info(f"Serial mode: {self.serial_port} @ {self.serial_baudrate} baud")
        else:
            # UDP connection (default)
            self.udp_port = self.config.get('udp_listen_port', 14550)
            self.drones = self.config.get('drones', {})
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", self.udp_port))
            self.logger.info(f"UDP mode: listening on 0.0.0.0:{self.udp_port}")
        
        # MAVLink encode/decode object using a dummy file
        self.mav = mavutil.mavlink.MAVLink(None)
        
        self.running = False
        self.recv_thread = None
        self.recv_callback = None

    def _load_config(self, path):
        with open(path, 'r') as f:
            return yaml.safe_load(f)

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
            self.logger.info("UDP受信を停止")

    def _recv_loop(self):
        if self.connection_type == 'serial':
            self._recv_loop_serial()
        else:
            self._recv_loop_udp()
    
    def _recv_loop_serial(self):
        """Receive MAVLink data from serial port (Pixhawk)"""
        while self.running:
            try:
                if not self.serial_conn or not self.serial_conn.is_open:
                    self.serial_conn = serial.Serial(
                        self.serial_port,
                        self.serial_baudrate,
                        timeout=1
                    )
                    self.logger.info(f"Serial port opened: {self.serial_port}")
                
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if self.recv_callback:
                        self.recv_callback(data, (self.serial_port, 0))
                else:
                    # データ未着時は短時間待機してCPUの過負荷を避ける
                    threading.Event().wait(0.01)
            except serial.SerialException as e:
                self.logger.warning(f"Serial接続エラー: {e}")
                if self.serial_conn:
                    try:
                        self.serial_conn.close()
                    except:
                        pass
                self.serial_conn = None
                threading.Event().wait(1)  # Retry after 1 second
            except Exception as e:
                self.logger.error(f"Serial受信エラー: {e}")
                threading.Event().wait(0.05)
    
    def _recv_loop_udp(self):
        """Receive MAVLink data from UDP port"""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                if self.recv_callback:
                    self.recv_callback(data, addr)
            except Exception as e:
                self.logger.error(f"UDP受信エラー: {e}")

    def send(self, system_id, data):
        """Send MAVLink data to the appropriate destination"""
        if self.connection_type == 'serial':
            # For serial mode, send back to Pixhawk
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.write(data)
                    self.logger.debug(f"Serial送信: {len(data)} bytes")
                except Exception as e:
                    self.logger.error(f"Serial送信エラー: {e}")
        else:
            # UDP mode: send to configured endpoint
            for drone_name, drone_info in self.drones.items():
                if drone_info.get('system_id') == system_id:
                    endpoint = drone_info.get('endpoint')
                    if endpoint:
                        ip, port = endpoint.split(":")
                        self.sock.sendto(data, (ip, int(port)))
                        self.logger.debug(f"送信: {ip}:{port} (system_id={system_id})")
                    break

    def send_to_system(self, system_id, data):
        """
        Send MAVLink data to a specific system.
        Alias for send() for clarity.
        """
        self.send(system_id, data)
