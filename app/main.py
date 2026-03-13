# main.py
from logging_config import setup_logging
import logging

from config_loader import resolve_config_path

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
    config_path = resolve_config_path()
    logger.info(f"設定ファイルを使用します: {config_path}")
    telemetry_store = TelemetryStore()
    mav_conn = MavlinkConnection(config_path)
    router = MessageRouter(mav_conn, telemetry_store)
    router.start()

    # RTCMインジェクション設定
    rtcm_enabled = mav_conn.config.get('rtcm_enabled', True)
    rtcm_port = mav_conn.config.get('rtcm_tcp_port', 15000)
    
    rtcm_reader = RtcmReader(port=rtcm_port, enabled=rtcm_enabled)
    rtcm_injector = RtcmInjector(enabled=rtcm_enabled)

    # RTCMデータ送信コールバックを設定
    def send_rtcm_message(frame_data):
        """MAVLinkメッセージ送信関数"""
        try:
            # 全ドローン（System ID 1, 2）へブロードキャスト
            mav_conn.send_to_system(1, frame_data)
            mav_conn.send_to_system(2, frame_data)
            logger.debug(f"RTCM frame sent to all systems: {len(frame_data)} bytes")
        except Exception as e:
            logger.error(f"Failed to send RTCM frame: {e}")

    rtcm_injector.set_send_callback(send_rtcm_message)

    # RTCMデータ受信時のコールバック
    def on_rtcm_data(data):
        """RTCMリーダーから受け取ったデータをインジェクターに渡す"""
        rtcm_injector.inject(data)

    rtcm_reader.register_callback(on_rtcm_data)
    rtcm_reader.start()

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
