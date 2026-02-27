# main.py
from logging_config import setup_logging
import logging


from mavlink.connection import MavlinkConnection
from mavlink.message_router import MessageRouter
from mavlink.telemetry_store import TelemetryStore
from mavlink.rtcm_reader import RtcmReader
from mavlink.rtcm_injector import RtcmInjector
import threading
import time

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("GCSアプリケーションが起動しました。")

    # 設定ファイルパス
    config_path = "config/gcs.yml"
    telemetry_store = TelemetryStore()
    mav_conn = MavlinkConnection(config_path)
    router = MessageRouter(mav_conn, telemetry_store)
    router.start()

    # RTCMインジェクション設定
    rtcm_enabled = True  # 有効/無効フラグ
    rtcm_reader = RtcmReader(enabled=rtcm_enabled)
    rtcm_injector = RtcmInjector(enabled=rtcm_enabled)

    # 仮のGPSシステム（実装に応じて置き換え）
    class DummyGPS:
        def send_rtcm_data(self, data):
            logger.info(f"DummyGPS received RTCM: {len(data)} bytes")
    gps_system = DummyGPS()

    def on_rtcm_data(data):
        rtcm_injector.inject(gps_system, data)

    rtcm_reader.register_callback(on_rtcm_data)

    # --- コマンドと制御のデモ ---
    from mavlink.command_dispatcher import CommandDispatcher
    from mavlink.guided_control import GuidedControl

    dispatcher = CommandDispatcher(mav_conn)
    guided = GuidedControl(mav_conn)

    # system_idを選択（例: 1）
    system_id = 1

    # アーム
    resp = dispatcher.send_arm(system_id)
    dispatcher.handle_response(resp)

    # 離陸（高度10m）
    resp = dispatcher.send_takeoff(system_id, altitude=10)
    dispatcher.handle_response(resp)

    # ガイド制御（NED座標 x=5, y=5, z=-10）
    resp = guided.set_position_target_local_ned(system_id, x=5, y=5, z=-10)
    guided.handle_response(resp)

    # 着陸
    resp = dispatcher.send_land(system_id)
    dispatcher.handle_response(resp)

    # ディスアーム
    resp = dispatcher.send_disarm(system_id)
    dispatcher.handle_response(resp)

    try:
        while True:
            # 1秒ごとに全システムIDのハートビートを表示
            all_data = telemetry_store.get_all()
            for sysid, messages in all_data.items():
                if 'HEARTBEAT' in messages:
                    logger.info(f"[system_id={sysid}] HEARTBEAT受信済み")
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("終了処理中...")
        router.stop()
        mav_conn.stop()
        rtcm_reader.stop()
        logger.info("RTCM injection stopped.")
