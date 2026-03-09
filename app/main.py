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

    # 仮のGPSシステム（MavlinkConnectionを利用してMavlinkのGPS_RTCM_DATAを送信するラッパー）
    class GpsSystemLink:
        def __init__(self, conn):
            self.conn = conn
            
        def send_rtcm_data(self, data):
            # System ID = 0 (Broadcast) for now, or based on UI selection
            logger.info(f"Sending RTCM to MAVLink network: {len(data)} bytes")
            # MAVLinkの gps_rtcm_data メッセージを送信
            flags = 0
            len_data = len(data)
            if len_data > 180:
                # チャンク化の簡易実装 (MVPとしてはそのまま送信または切り詰め)
                data = data[:180]
                len_data = len(data)
                
            # dataは180要素の配列である必要があるのでゼロ埋めする
            padded_data = list(bytearray(data) + b'\x00' * (180 - len_data))
            
            try:
                # pymavlinkのオブジェクトを使ってパックし、UDPで送信
                msg = self.conn.mav.gps_rtcm_data_encode(flags, len_data, padded_data)
                packet = msg.pack(self.conn.mav)
                # 全ドローン（system_id=0等）へのブロードキャスト、もしくは登録済みへ
                self.conn.send(1, packet) # まずはSystem 1宛に送ってみる
                self.conn.send(2, packet) # 同様にSystem 2宛
            except Exception as e:
                logger.error(f"Failed to encode/send RTCM: {e}")

    gps_system = GpsSystemLink(mav_conn)

    def on_rtcm_data(data):
        rtcm_injector.inject(gps_system, data)

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
