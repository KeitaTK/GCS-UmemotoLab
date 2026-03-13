#!/usr/bin/env python3
"""
GCS Backend Server (headless)
Runs on Raspberry Pi and forwards MAVLink messages from Pixhawk to remote GCS.
"""

from logging_config import setup_logging
import logging

from mavlink.connection import MavlinkConnection
from mavlink.message_router import MessageRouter
from mavlink.telemetry_store import TelemetryStore
from mavlink.rtcm_reader import RtcmReader
from mavlink.rtcm_injector import RtcmInjector
import threading
import time
import sys

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("GCS Backend Server starting (headless mode)...")

    # 設定ファイルパス
    config_path = "config/gcs.yml"
    telemetry_store = TelemetryStore()
    mav_conn = MavlinkConnection(config_path)
    router = MessageRouter(mav_conn, telemetry_store)
    
    # Start message router in a daemon thread
    router.start()
    logger.info("MessageRouter started.")

    # RTCMインジェクション設定
    rtcm_enabled = mav_conn.config.get('rtcm_enabled', True)
    rtcm_tcp_port = mav_conn.config.get('rtcm_tcp_port', 5000)
    
    rtcm_reader = RtcmReader(port=rtcm_tcp_port, enabled=rtcm_enabled)
    rtcm_injector = RtcmInjector(mav_conn, enabled=rtcm_enabled)
    
    # Start RTCM reader thread
    if rtcm_enabled:
        rtcm_thread = threading.Thread(target=rtcm_reader.read_stream, daemon=True)
        rtcm_thread.start()
        logger.info(f"RTCM Reader started on port {rtcm_tcp_port}.")

    # Keep the process alive and log telemetry periodically
    try:
        while True:
            time.sleep(5)
            drone_ids = telemetry_store.get_all_drone_ids()
            if drone_ids:
                logger.info(f"Active drones: {drone_ids}")
                for drone_id in drone_ids:
                    hb = telemetry_store.get_heartbeat(drone_id)
                    if hb:
                        logger.info(f"  Drone {drone_id}: type={hb.type}, armed={hb.base_mode & 0x80}")
            else:
                logger.warning("No drone heartbeats received yet.")
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
