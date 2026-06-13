# main.py
import sys
import os
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging
import logging

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GCS-UmemotoLab")
    parser.add_argument(
        "--native",
        action="store_true",
        help="Launch PySide6 GUI (default: start FastAPI web server)",
    )
    parser.add_argument(
        "--host",
        default="100.95.30.60",
        help="Server bind address (default: 100.95.30.60)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    if args.native:
        # =====================================================================
        #  Native (GUI) mode: PySide6
        # =====================================================================
        logger.info("GCSアプリケーションが起動しました。（GUIモード）")

        from rtk_tools.config_loader import resolve_config_path
        from mavlink.connection import MavlinkConnection
        from mavlink.message_router import MessageRouter
        from rtk_tools.telemetry_store import TelemetryStore
        from rtk_tools.rtcm_reader import RtcmReader
        from rtk_tools.rtcm_injector import RtcmInjector
        import threading

        # 設定ファイルパス
        config_path = resolve_config_path()
        logger.info(f"設定ファイルを使用します: {config_path}")
        telemetry_store = TelemetryStore()
        mav_conn = MavlinkConnection(config_path)

        # --- コマンド制御の初期化（MessageRouter前に行う） ---
        from rtk_tools.command_dispatcher import CommandDispatcher
        from rtk_tools.guided_control import GuidedControl

        dispatcher = CommandDispatcher(mav_conn)
        dispatcher.guided = GuidedControl(mav_conn)

        # MessageRouter を CommandDispatcher と一緒に初期化
        router = MessageRouter(mav_conn, telemetry_store, command_dispatcher=dispatcher)
        router.start()

        # UI起動前に、バックグラウンドスレッドで数秒後に送信する
        def request_streams():
            import time

            logger.info("Pixhawk接続安定化のため待機中...")
            time.sleep(2.0)

            try:
                logger.info("Pixhawkにデータストリームを要求します")
                # pymavlinkの純正エンコーダーを使用して msgid=66 を生成
                msg = mav_conn.mav.request_data_stream_encode(
                    1,  # target_system (Pixhawk本体)
                    0,  # target_component (0にすると「全機能」宛てのブロードキャストになり確実です)
                    0,  # req_stream_id (0: 全データ)
                    5,  # req_message_rate (5Hz)
                    1   # start_stop (1: 送信開始)
                )

                # メッセージをバイナリ（バイト列）に変換して送信
                frame = msg.pack(mav_conn.mav)
                mav_conn.send(1, frame)

                logger.info("データストリーム要求を送信しました！")
            except Exception as e:
                logger.error(f"データストリーム要求の送信に失敗しました: {e}")

        threading.Thread(target=request_streams, daemon=True).start()

        # RTCMインジェクション設定
        rtcm_enabled = mav_conn.config.get('rtcm_enabled', True)
        rtcm_host = mav_conn.config.get('rtcm_host', '127.0.0.1')
        rtcm_port = mav_conn.config.get('rtcm_tcp_port', 15000)

        rtcm_reader = RtcmReader(host=rtcm_host, port=rtcm_port, enabled=rtcm_enabled)
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

        # UI起動
        from PySide6.QtWidgets import QApplication
        from ui.main_window import MainWindow

        app = QApplication(sys.argv)
        window = MainWindow(telemetry_store, dispatcher=dispatcher, connection=mav_conn, rtcm_reader=rtcm_reader)
        window.show()

        logger.info("GUIイベントループを開始します。")
        exit_code = app.exec()

        logger.info("終了処理中...")
        router.stop()
        mav_conn.stop()
        rtcm_reader.stop()
        logger.info("RTCM injection stopped.")
        sys.exit(exit_code)

    else:
        # =====================================================================
        #  Default: Web Server mode (FastAPI)
        # =====================================================================
        logger.info(f"GCS Webサーバーを起動します: {args.host}:{args.port}")

        import uvicorn
        uvicorn.run(
            "app.server:app",
            host=args.host,
            port=args.port,
            log_level="info",
            reload=False,
        )
