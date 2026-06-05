#!/usr/bin/env python3
"""
GCS Backend Server (headless)
Runs on Raspberry Pi and forwards MAVLink messages from Pixhawk to remote GCS.
"""

import sys
sys.path.insert(0, '.')

from logging_config import setup_logging
import logging

from config_loader import resolve_config_path
from mavlink.connection import MavlinkConnection
from mavlink.message_router import MessageRouter
from mavlink.telemetry_store import TelemetryStore
from mavlink.rtcm_reader import RtcmReader
from mavlink.rtcm_injector import RtcmInjector
import time

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("GCS Backend Server starting (headless mode)...")

    try:
        # 設定ファイルパス
        config_path = resolve_config_path()
        logger.info(f"設定ファイルを使用します: {config_path}")
        telemetry_store = TelemetryStore()
        mav_conn = MavlinkConnection(config_path)
        router = MessageRouter(mav_conn, telemetry_store)

        # RTCMインジェクション設定
        rtcm_enabled = mav_conn.config.get('rtcm_enabled', True)
        rtcm_host = mav_conn.config.get('rtcm_host', '127.0.0.1')
        rtcm_port = mav_conn.config.get('rtcm_tcp_port', 15000)

        rtcm_reader = RtcmReader(host=rtcm_host, port=rtcm_port, enabled=rtcm_enabled)
        rtcm_injector = RtcmInjector(enabled=rtcm_enabled)

        def send_rtcm_message(frame_data):
            """MAVLinkメッセージ送信関数"""
            try:
                # serial接続時はsystem_idは無視され同一ポートに送信される
                mav_conn.send_to_system(1, frame_data)
                mav_conn.send_to_system(2, frame_data)
                logger.debug(f"RTCM frame sent: {len(frame_data)} bytes")
            except Exception as e:
                logger.error(f"Failed to send RTCM frame: {e}")

        def on_rtcm_data(data):
            """RTCMリーダーから受け取ったデータをインジェクターに渡す"""
            rtcm_injector.inject(data)

        rtcm_injector.set_send_callback(send_rtcm_message)
        rtcm_reader.register_callback(on_rtcm_data)
        
        # Start message router in a daemon thread
        router.start()
        logger.info(f"MessageRouter started. Connection type: {mav_conn.connection_type}")
        rtcm_reader.start()
        logger.info(f"RTCM injection started: enabled={rtcm_enabled}, source={rtcm_host}:{rtcm_port}")

        # Keep the process alive and log telemetry periodically
        last_log_time = time.time()
        while True:
            time.sleep(1)
            
            # Log status every 5 seconds
            current_time = time.time()
            if current_time - last_log_time >= 5:
                drone_ids = telemetry_store.get_all_drone_ids()
                if drone_ids:
                    logger.info(f"Active drones: {drone_ids}")
                    for drone_id in drone_ids:
                        hb = telemetry_store.get_heartbeat(drone_id)
                        if hb:
                            # HEARTBEATの保持形式が実行環境で異なる場合に備えて防御的に処理
                            if hasattr(hb, 'base_mode'):
                                armed = (hb.base_mode & 0x80) != 0
                                logger.info(
                                    f"  Drone {drone_id}: type={getattr(hb, 'type', 'n/a')}, "
                                    f"armed={armed}, mode={getattr(hb, 'custom_mode', 'n/a')}"
                                )
                            else:
                                logger.info(f"  Drone {drone_id}: heartbeat received ({type(hb).__name__})")
                else:
                    logger.debug("Waiting for drone heartbeats...")
                last_log_time = current_time
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        try:
            rtcm_reader.stop()
        except Exception:
            pass
        try:
            router.stop()
        except Exception:
            pass
        try:
            mav_conn.stop()
        except Exception:
            pass
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

