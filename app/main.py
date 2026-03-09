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
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

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

    # --- コマンドと制御のデモ（初期化のみ） ---
    from mavlink.command_dispatcher import CommandDispatcher
    from mavlink.guided_control import GuidedControl

    dispatcher = CommandDispatcher(mav_conn)
    guided = GuidedControl(mav_conn)

    # UI起動
    app = QApplication(sys.argv)
    window = MainWindow(telemetry_store, dispatcher=dispatcher)
    window.show()

    logger.info("GUIイベントループを開始します。")
    exit_code = app.exec()

    logger.info("終了処理中...")
    router.stop()
    mav_conn.stop()
    rtcm_reader.stop()
    logger.info("RTCM injection stopped.")
    sys.exit(exit_code)
