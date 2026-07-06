#!/usr/bin/env python3
"""
GCS Backend Server (Raspberry Pi headless mode)

Raspberry Pi 上で動作し、Pixhawk から受信した MAVLink メッセージを
リモート GCS に転送する。また、RTK 補正データ（RTCM）を PC 側の
基地局から受信して Pixhawk に注入する。

使用方法:
  cd ~/GCS-UmemotoLab/raspi
  python backend_server.py

設定:
  raspi/config.yml（または RASPI_CONFIG_PATH 環境変数で指定）
"""

import sys
import os
from pathlib import Path

# リポジトリルートを sys.path に追加
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import logging
import time

from rtk_tools.config_loader import load_config
from app.logging_config import setup_logging
from app.mavlink.connection import MavlinkConnection
from app.mavlink.message_router import MessageRouter
from app.mavlink.telemetry_store import TelemetryStore
from app.rtk_tools.rtcm_reader import RtcmReader
from app.rtk_tools.rtcm_injector import RtcmInjector


def _resolve_raspi_config() -> dict:
    """Raspi 設定を解決する。
    環境変数 RASPI_CONFIG_PATH があればそれを、なければ raspi/config.yml を使う。
    """
    import os
    from pathlib import Path
    env = os.environ.get("RASPI_CONFIG_PATH")
    if env:
        return load_config(env)
    # raspi/config.yml を明示指定
    repo_root = Path(__file__).resolve().parent.parent
    raspi_config = repo_root / "raspi" / "config.yml"
    if raspi_config.exists():
        return load_config(str(raspi_config))
    # fallback: デフォルトの config.yml を読み込む
    return load_config()


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("GCS Backend Server (Raspi) starting...")

    try:
        # 1. Raspi 設定を読み込む
        config = _resolve_raspi_config()
        logger.info("Config loaded")

        # 2. 接続設定は MavlinkConnection に dict として渡す
        conn_cfg = config.get("connection", {})
        rtcm_cfg = config.get("rtcm", {})
        drones_cfg = config.get("drones", {})

        mav_config = {
            "connection_type": conn_cfg.get("type", "serial"),
            "serial_port": conn_cfg.get("serial_port", "/dev/ttyAMA0"),
            "serial_baudrate": conn_cfg.get("serial_baudrate", 115200),
            "serial_rtscts": conn_cfg.get("serial_rtscts", False),
            "udp_listen_port": conn_cfg.get("udp_listen_port", 14550),
            "drones": {},
            "rtcm_enabled": rtcm_cfg.get("enabled", True),
            "rtcm_host": rtcm_cfg.get("host", "127.0.0.1"),
            "rtcm_tcp_port": rtcm_cfg.get("port", 2101),
        }

        # drones を flat 形式に変換
        if isinstance(drones_cfg, dict):
            mav_config["drones"] = drones_cfg
        elif isinstance(drones_cfg, list):
            for i, d in enumerate(drones_cfg):
                sid = d.get("system_id", i + 1)
                mav_config["drones"][f"drone{sid}"] = {
                    "system_id": sid,
                    "endpoint": d.get("endpoint", "127.0.0.1:14550"),
                    "name": d.get("name", f"Drone {sid}"),
                }

        # 3. GCS側のクラスを初期化
        telemetry_store = TelemetryStore()
        mav_conn = MavlinkConnection(mav_config)
        router = MessageRouter(mav_conn, telemetry_store)

        # 4. RTCM 設定
        rtcm_cfg = config.get("rtcm", {})
        rtcm_enabled = rtcm_cfg.get("enabled", True)
        rtcm_host = rtcm_cfg.get("host", "127.0.0.1")
        rtcm_port = rtcm_cfg.get("port", 2101)

        rtcm_reader = RtcmReader(host=rtcm_host, port=rtcm_port, enabled=rtcm_enabled)
        rtcm_injector = RtcmInjector(enabled=rtcm_enabled)

        def send_rtcm_message(frame_data):
            try:
                mav_conn.send_to_system(1, frame_data)
                logger.debug(f"RTCM frame sent: {len(frame_data)} bytes")
            except Exception as e:
                logger.error(f"Failed to send RTCM frame: {e}")

        def on_rtcm_data(data):
            rtcm_injector.inject(data)

        rtcm_injector.set_send_callback(send_rtcm_message)
        rtcm_reader.register_callback(on_rtcm_data)

        # 5. 起動
        router.start()
        logger.info(f"MessageRouter started. Connection: {mav_conn.connection_type}")
        rtcm_reader.start()
        logger.info(f"RTCM injection: enabled={rtcm_enabled}, source={rtcm_host}:{rtcm_port}")

        # 6. メインループ
        last_log_time = time.time()
        while True:
            time.sleep(1)
            now = time.time()
            if now - last_log_time >= 5:
                drone_ids = telemetry_store.get_all_drone_ids()
                if drone_ids:
                    logger.info(f"Active drones: {drone_ids}")
                    for drone_id in drone_ids:
                        hb = telemetry_store.get_heartbeat(drone_id)
                        if hb:
                            if hasattr(hb, "base_mode"):
                                armed = (hb.base_mode & 0x80) != 0
                                logger.info(
                                    f"  Drone {drone_id}: type={getattr(hb, 'type', 'n/a')}, "
                                    f"armed={armed}, mode={getattr(hb, 'custom_mode', 'n/a')}"
                                )
                            else:
                                logger.info(
                                    f"  Drone {drone_id}: heartbeat ({type(hb).__name__})"
                                )
                else:
                    logger.debug("Waiting for drone heartbeats...")
                last_log_time = now

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        for obj in ("rtcm_reader", "router", "mav_conn"):
            try:
                locals()[obj].stop()
            except Exception:
                pass
        logger.info("GCS Backend Server stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()