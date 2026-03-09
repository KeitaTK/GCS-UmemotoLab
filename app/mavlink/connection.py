# MavlinkConnection: UDP入出力用
import socket
import threading
import logging
import yaml

class MavlinkConnection:
    def __init__(self, config_path):
        from pymavlink import mavutil
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)
        self.udp_port = self.config.get('udp_listen_port', 14550)
        self.drones = self.config.get('drones', {})
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.udp_port))
        
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
        self.logger.info(f"UDP受信を開始: 0.0.0.0:{self.udp_port}")

    def stop(self):
        self.running = False
        if self.recv_thread:
            self.recv_thread.join()
        self.sock.close()
        self.logger.info("UDP受信を停止")

    def _recv_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                if self.recv_callback:
                    self.recv_callback(data, addr)
            except Exception as e:
                self.logger.error(f"UDP受信エラー: {e}")

    def send(self, system_id, data):
        # system_idから送信先エンドポイントを取得
        for drone_name, drone_info in self.drones.items():
            if drone_info.get('system_id') == system_id:
                endpoint = drone_info.get('endpoint')
                if endpoint:
                    ip, port = endpoint.split(":")
                    self.sock.sendto(data, (ip, int(port)))
                    self.logger.debug(f"送信: {ip}:{port} (system_id={system_id})")
                break
        def send_command_long(self, target_system, target_component, command, confirmation, param1=0, param2=0, param3=0, param4=0, param5=0, param6=0, param7=0):
            """
            MAVLink COMMAND_LONG送信
            """
            # ここでMAVLinkパケット生成（例: pymavlink使用）
            # msg = mavutil.mavlink.MAVLink_command_long_message(...)
            # self.send(msg)
            print(f"[LOG] COMMAND_LONG送信: system={target_system}, component={target_component}, command={command}, params={[param1,param2,param3,param4,param5,param6,param7]}")
            # レスポンス処理（必要なら）

        def send_set_position_target_local_ned(self, target_system, target_component, x, y, z, vx, vy, vz, yaw):
            """
            SET_POSITION_TARGET_LOCAL_NED送信
            """
            # ここでMAVLinkパケット生成（例: pymavlink使用）
            # msg = mavutil.mavlink.MAVLink_set_position_target_local_ned_message(...)
            # self.send(msg)
            print(f"[LOG] SET_POSITION_TARGET_LOCAL_NED送信: system={target_system}, component={target_component}, pos=({x},{y},{z}), vel=({vx},{vy},{vz}), yaw={yaw}")
            # レスポンス処理（必要なら）
