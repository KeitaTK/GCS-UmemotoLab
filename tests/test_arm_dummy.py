"""
ダミードローンを使ったアームテスト
実機が無い環境でも arm() のロジックを検証します。

使い方:
  cd GCS-UmemotoLab/app && python ../tests/test_arm_dummy.py
"""
import sys
import os
import time
import threading
import subprocess
import signal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

from mavlink.connection import MavlinkConnection
from mavlink.message_router import MessageRouter
from rtk_tools.telemetry_store import TelemetryStore
from rtk_tools.command_dispatcher import CommandDispatcher
import yaml
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("arm_dummy_test")

# テスト用のUDP設定を動的に生成
TEST_CONFIG_PATH = "/tmp/gcs_test_arm.yml"

def create_test_config():
    config = {
        'connection_type': 'udp',
        'udp_listen_port': 14551,
        'drones': {
            'drone1': {
                'system_id': 1,
                'endpoint': '127.0.0.1:14552'
            }
        },
        'rtcm_enabled': False,
    }
    with open(TEST_CONFIG_PATH, 'w') as f:
        yaml.dump(config, f)
    return TEST_CONFIG_PATH

def main():
    # --- Step 1: ダミードローン起動（別プロセス） ---
    logger.info("=== Step 1: ダミードローン起動 ===")
    dummy_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', 'app', 'dummy_sitl_multi.py'
    )
    
    # dummy_sitl_multi.py がない場合は、簡易ダミードローンをこのプロセス内で起動
    dummy_available = os.path.exists(dummy_script)
    
    # 簡易ダミードローンをスレッドで起動
    # 双方向通信: raw socket を使用
    import socket as sock_module
    from pymavlink import mavutil
    
    def run_dummy():
        # 出力ソケット: GCS にハートビート送信（sendtoで送るのでconnect不要）
        out_sock = sock_module.socket(sock_module.AF_INET, sock_module.SOCK_DGRAM)
        
        # 入力ソケット: GCS からのコマンド受信 (14552番ポート)
        in_sock = sock_module.socket(sock_module.AF_INET, sock_module.SOCK_DGRAM)
        in_sock.setsockopt(sock_module.SOL_SOCKET, sock_module.SO_REUSEADDR, 1)
        in_sock.bind(('127.0.0.1', 14552))
        in_sock.settimeout(0.1)
        
        # pymavlink の MAVLink エンコーダ
        mav = mavutil.mavlink.MAVLink(None)
        mav.srcSystem = 1
        mav.srcComponent = 1
        
        logger.info(f"🤖 Dummy Drone 1 started")
        logger.info(f"   Output → 127.0.0.1:14551 (GCS)")
        logger.info(f"   Input  ← 127.0.0.1:14552 (GCS commands)")
        
        # ダミードローンの状態
        drone_state = {'armed': False}
        
        # GCS が使う MAVLink デコーダ（受信データ解析用）
        recv_mav = mavutil.mavlink.MAVLink(None)
        
        # コマンド受信スレッド
        def listen():
            while True:
                try:
                    data, addr = in_sock.recvfrom(4096)
                    # MAVLink メッセージを解析
                    msgs = recv_mav.parse_buffer(data)
                    for msg in msgs:
                        if msg is None:
                            continue
                        msg_type = msg.get_type()
                        if msg_type == 'COMMAND_LONG':
                            cmd = msg.command
                            logger.info(f"📥 [Drone 1] COMMAND_LONG: cmd={cmd}, "
                                       f"param1={msg.param1}, confirmation={msg.confirmation}")
                            
                            if cmd == 176:  # DO_SET_MODE
                                logger.info(f"   → Mode set command (param1={msg.param1})")
                            elif cmd == 400:  # ARM/DISARM
                                param1 = msg.param1
                                drone_state['armed'] = (param1 == 1)
                                logger.info(f"   → {'🟢 ARM' if drone_state['armed'] else '🔴 DISARM'} command")
                            
                            # ACKを送信 (MAV_RESULT_ACCEPTED = 0)
                            ack_msg = mav.command_ack_encode(cmd, 0)
                            ack_data = ack_msg.pack(mav)
                            out_sock.sendto(ack_data, ('127.0.0.1', 14551))
                            logger.info(f"📤 [Drone 1] COMMAND_ACK sent: cmd={cmd}")
                except sock_module.timeout:
                    pass
                except Exception as e:
                    logger.info(f"📨 [Drone 1] Listener error: {type(e).__name__}: {e}")
                time.sleep(0.01)
        
        threading.Thread(target=listen, daemon=True).start()
        
        # ハートビート送信ループ
        while True:
            base_mode = mavutil.mavlink.MAV_MODE_GUIDED_ARMED if drone_state['armed'] else mavutil.mavlink.MAV_MODE_GUIDED_DISARMED
            hb = mav.heartbeat_encode(
                type=mavutil.mavlink.MAV_TYPE_QUADROTOR,
                autopilot=mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                base_mode=base_mode,
                custom_mode=4,
                system_status=mavutil.mavlink.MAV_STATE_STANDBY,
                mavlink_version=3
            )
            out_sock.sendto(hb.pack(mav), ('127.0.0.1', 14551))
            time.sleep(1)
    
    dummy_thread = threading.Thread(target=run_dummy, daemon=True)
    dummy_thread.start()
    time.sleep(1.5)
    
    # --- Step 2: GCS 接続 ---
    logger.info("=== Step 2: GCS 接続 ===")
    config_path = create_test_config()
    logger.info(f"Test config: {config_path}")
    
    telemetry_store = TelemetryStore()
    mav_conn = MavlinkConnection(config_path)
    dispatcher = CommandDispatcher(mav_conn)
    
    # ACK callback
    ack_received = threading.Event()
    def on_ack(sysid, cmd_id, result, status_str):
        logger.info(f"📡 COMMAND_ACK: sysid={sysid}, cmd={cmd_id}, result={status_str}")
        if cmd_id == 400:
            ack_received.set()
    dispatcher._ack_callbacks.append(on_ack)
    
    router = MessageRouter(mav_conn, telemetry_store, command_dispatcher=dispatcher)
    router.start()
    
    logger.info("Waiting for heartbeat from dummy drone...")
    time.sleep(3)
    
    # --- Step 3: 現在の状態確認 ---
    logger.info("=== Step 3: 状態確認 ===")
    active_ids = telemetry_store.get_all_drone_ids()
    logger.info(f"アクティブなドローン: {active_ids}")
    
    hb = telemetry_store.get_heartbeat(1)
    if hb:
        armed = (hb.base_mode & 0x80) != 0
        logger.info(f"現在の状態: {'🟢 ARMED' if armed else '🔴 DISARMED'}")
    
    # --- Step 4: アーム送信 ---
    logger.info("=== Step 4: 🚀 アーム送信 ===")
    dispatcher.arm(system_id=1, component_id=1)
    logger.info("アームコマンド送信完了（モードセット→0.3秒後→アーム）")
    
    # arm() は Timer(0.3) + ACK待機で最大2秒程度かかる
    time.sleep(2)
    
    # --- Step 5: 結果確認 ---
    logger.info("=== Step 5: 結果確認 ===")
    hb = telemetry_store.get_heartbeat(1)
    if hb:
        armed = (hb.base_mode & 0x80) != 0
        logger.info(f"アーム後状態: {'🟢 ARMED' if armed else '🔴 DISARMED'}")
    
    with dispatcher._pending_lock:
        for key, info in dispatcher._pending_commands.items():
            logger.info(f"  ACK track: sysid={info['system_id']}, cmd={info['command_id']}, "
                       f"desc={info['description']}, status={info['status']}")
    
    if ack_received.is_set():
        logger.info("✅ ACK受信成功！アーム可能です")
    else:
        logger.info("⚠️  ACK未受信（ダミードローンがACKを返していない可能性あり）")
    
    # --- 後片付け ---
    logger.info("=== テスト終了 ===")
    router.stop()
    mav_conn.stop()
    time.sleep(0.5)
    os.remove(TEST_CONFIG_PATH)

if __name__ == "__main__":
    main()
