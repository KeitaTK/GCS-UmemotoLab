"""
実機アームテストスクリプト
使い方:
  cd GCS-UmemotoLab/app
  python ../tests/test_arm_live.py [system_id]

system_id 省略時は 1 を使用
"""
import sys
import os
import time
import threading

# app/ ディレクトリを sys.path に追加
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

from rtk_tools.config_loader import resolve_config_path
from mavlink.connection import MavlinkConnection
from mavlink.message_router import MessageRouter
from rtk_tools.telemetry_store import TelemetryStore
from rtk_tools.command_dispatcher import CommandDispatcher
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("arm_test")

def main():
    system_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    config_path = resolve_config_path()
    logger.info(f"Config: {config_path}")
    
    telemetry_store = TelemetryStore()
    mav_conn = MavlinkConnection(config_path)
    dispatcher = CommandDispatcher(mav_conn)
    
    # ACK callback を登録
    def on_ack(sysid, cmd_id, result, status_str):
        logger.info(f"📡 COMMAND_ACK: sysid={sysid}, cmd={cmd_id}, result={status_str}")
    
    dispatcher._ack_callbacks.append(on_ack)
    
    # MessageRouter で受信開始
    router = MessageRouter(mav_conn, telemetry_store, command_dispatcher=dispatcher)
    router.start()
    
    logger.info(f"接続中... 5秒待機 (実機からのハートビートを待つ)")
    time.sleep(5)
    
    # アクティブなドローン一覧
    active_ids = telemetry_store.get_all_drone_ids()
    logger.info(f"アクティブなドローン: {active_ids}")
    
    if system_id not in active_ids:
        logger.warning(f"⚠️  System ID {system_id} がアクティブ一覧にありません。それでもアームを試みます。")
    
    # 現在のアーム状態を確認
    hb = telemetry_store.get_heartbeat(system_id)
    if hb:
        armed = (hb.base_mode & 0x80) != 0
        logger.info(f"現在の状態: {'🟢 ARMED' if armed else '🔴 DISARMED'}")
    
    # アーム送信
    logger.info(f"🚀 アーム送信中... (system_id={system_id})")
    dispatcher.arm(system_id, component_id=1)
    
    # 0.5秒待ってACKを待つ (armはTimerで0.3秒遅延するため)
    time.sleep(2)
    
    # 状態確認
    hb = telemetry_store.get_heartbeat(system_id)
    if hb:
        armed = (hb.base_mode & 0x80) != 0
        logger.info(f"アーム後状態: {'🟢 ARMED' if armed else '🔴 DISARMED'}")
    
    # ACK追跡状態を確認
    with dispatcher._pending_lock:
        for key, info in dispatcher._pending_commands.items():
            logger.info(f"  ACK track: sysid={info['system_id']}, cmd={info['command_id']}, "
                       f"desc={info['description']}, status={info['status']}")
    
    # 後片付け
    logger.info("テスト完了。5秒後に終了します...")
    time.sleep(5)
    router.stop()
    mav_conn.stop()
    logger.info("終了")

if __name__ == "__main__":
    main()
