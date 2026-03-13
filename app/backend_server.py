#!/usr/bin/env python3
"""
GCS Backend Server (headless)
Runs on Raspberry Pi and forwards MAVLink messages from Pixhawk to remote GCS.
"""

import sys
sys.path.insert(0, '.')

from logging_config import setup_logging
import logging

from mavlink.connection import MavlinkConnection
from mavlink.message_router import MessageRouter
from mavlink.telemetry_store import TelemetryStore
import time

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("GCS Backend Server starting (headless mode)...")

    try:
        # 設定ファイルパス
        config_path = "config/gcs.yml"
        telemetry_store = TelemetryStore()
        mav_conn = MavlinkConnection(config_path)
        router = MessageRouter(mav_conn, telemetry_store)
        
        # Start message router in a daemon thread
        router.start()
        logger.info(f"MessageRouter started. Connection type: {mav_conn.connection_type}")

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
                            armed = (hb.base_mode & 0x80) != 0
                            logger.info(f"  Drone {drone_id}: type={hb.type}, armed={armed}, mode={hb.custom_mode}")
                else:
                    logger.debug("Waiting for drone heartbeats...")
                last_log_time = current_time
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

