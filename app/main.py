# main.py
import sys
import os
import argparse
import subprocess
import socket
import signal
import atexit

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging
import logging
import time


# ── Tailscale SSH Tunnel 自動セットアップ ──────────────────────────

_tunnel_processes = []  # cleanup用


def _setup_tailscale_tunnel(config: dict, logger: logging.Logger):
    """SSHトンネル＋socat＋ブリッジを自動起動（Tailscale経由の実機接続用）。

    UDP直結ができないTailscale環境で、TCPベースのリレーを構築する。
    失敗してもエラーをログに残すだけで GCS の起動は続行する。
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    drones = config.get("drones", {})
    needs_tunnel = False
    for d in drones.values():
        ep = d.get("endpoint", "")
        if ep.startswith("127.0.0.1"):
            needs_tunnel = True
            break
    if not needs_tunnel:
        logger.info("ローカル接続モード（SSHトンネル不要）")
        return

    tunnel_enabled = config.get("tailscale_tunnel", {}).get("enabled", True)
    if not tunnel_enabled:
        logger.info("SSHトンネル自動セットアップ: 無効化されています")
        return

    ssh_host = config.get("tailscale_tunnel", {}).get("ssh_host", "raspi")
    raspi_tcp_port = config.get("tailscale_tunnel", {}).get("raspi_tcp_port", 14551)
    local_tcp_port = config.get("tailscale_tunnel", {}).get("local_tcp_port", 14551)
    bridge_udp_port = config.get("tailscale_tunnel", {}).get("bridge_udp_port", 14552)

    logger.info("=== Tailscale SSHトンネル自動セットアップ開始 ===")

    # 1) Raspi 側 socat 起動
    logger.info(f"[1/3] Raspi socat起動: TCP:{raspi_tcp_port}→UDP:14550")
    try:
        subprocess.run(["ssh", "-o", "ConnectTimeout=10", ssh_host,
            f"ss -tlnp | grep -q ':{raspi_tcp_port}' || "
            f"socat TCP-LISTEN:{raspi_tcp_port},fork,reuseaddr UDP:localhost:14550 &"],
            timeout=12, capture_output=True)
        logger.info("  → Raspi socat 起動完了")
    except subprocess.TimeoutExpired:
        logger.warning("  → Raspi socat SSH タイムアウト")
    except Exception as e:
        logger.warning(f"  → Raspi socat 起動失敗: {e}")

    # 2) SSH トンネル確立
    logger.info(f"[2/3] SSHトンネル確立: localhost:{local_tcp_port}→{ssh_host}:{raspi_tcp_port}")
    try:
        proc = subprocess.Popen(["ssh", "-N", "-L", f"{local_tcp_port}:localhost:{raspi_tcp_port}",
            "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30",
            "-o", "ExitOnForwardFailure=yes", ssh_host],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _tunnel_processes.append(proc)
        time.sleep(2)
        logger.info("  → SSHトンネル確立完了")
    except Exception as e:
        logger.warning(f"  → SSHトンネル確立失敗: {e}")

    # 3) ローカル UDP↔TCP ブリッジ起動
    logger.info(f"[3/3] ローカルブリッジ起動: UDP:{bridge_udp_port}↔TCP:{local_tcp_port}")
    bridge_script = os.path.join(project_root, "scripts", "udp_tcp_bridge.py")
    if not os.path.exists(bridge_script):
        logger.warning(f"  → ブリッジスクリプトが見つかりません: {bridge_script}")
        return

    try:
        proc = subprocess.Popen([sys.executable, bridge_script,
            str(bridge_udp_port), str(local_tcp_port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _tunnel_processes.append(proc)
        time.sleep(1)
        logger.info("  → ローカルブリッジ起動完了")
    except Exception as e:
        logger.warning(f"  → ブリッジ起動失敗: {e}")

    logger.info("=== Tailscale SSHトンネル自動セットアップ完了 ===")


def _cleanup_tunnel():
    for proc in _tunnel_processes:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GCS-UmemotoLab")
    parser.add_argument("--native", action="store_true",
        help="Launch PySide6 GUI (default: start FastAPI web server)")
    parser.add_argument("--host", default=None,
        help="Server bind address (default: from config.yml)")
    parser.add_argument("--port", type=int, default=None,
        help="Server port (default: from config.yml)")
    args = parser.parse_args()

    from rtk_tools.config_loader import load_config
    _cfg = load_config()
    setup_logging(_cfg)
    logger = logging.getLogger(__name__)

    if args.native:
        # =====================================================================
        #  Native (GUI) mode: PySide6
        # =====================================================================
        logger.info("GCSアプリケーションが起動しました。（GUIモード）")

        from rtk_tools.config_loader import load_config
        from mavlink.connection import MavlinkConnection
        from mavlink.message_router import MessageRouter
        from rtk_tools.telemetry_store import TelemetryStore
        from rtk_tools.rtcm_serial_reader import RtcmSerialReader
        from rtk_tools.rtcm_injector import RtcmInjector
        from rtk_tools.rtcm_logger import RtcmLogger
        import threading

        config = load_config()
        logger.info(f"設定を読み込みました: connection.type={config.get('connection', {}).get('type', 'udp')}")
        telemetry_store = TelemetryStore()

        _setup_tailscale_tunnel(config, logger)
        atexit.register(_cleanup_tunnel)

        mav_conn = MavlinkConnection(config)

        from rtk_tools.command_dispatcher import CommandDispatcher
        from rtk_tools.guided_control import GuidedControl

        dispatcher = CommandDispatcher(mav_conn)
        dispatcher.guided = GuidedControl(mav_conn)

        router = MessageRouter(mav_conn, telemetry_store, command_dispatcher=dispatcher)
        router.start()

        def request_streams():
            import time
            logger.info("Pixhawk接続安定化のため待機中...")
            time.sleep(2.0)
            try:
                logger.info("Pixhawkにデータストリームを要求します")
                msg = mav_conn.mav.request_data_stream_encode(1, 0, 0, 5, 1)
                frame = msg.pack(mav_conn.mav)
                mav_conn.send(1, frame)
                logger.info("データストリーム要求を送信しました！")
            except Exception as e:
                logger.error(f"データストリーム要求の送信に失敗しました: {e}")

        threading.Thread(target=request_streams, daemon=True).start()

        rtcm_cfg = config.get('rtcm', {})
        rtcm_enabled = rtcm_cfg.get('enabled', True)
        rtcm_serial_port = rtcm_cfg.get('f9p_serial_port', 'COM8')
        rtcm_baudrate = rtcm_cfg.get('f9p_baudrate', 115200)

        # F9Pシリアル直読み + Queue
        rtcm_serial_reader = RtcmSerialReader(
            serial_port=rtcm_serial_port,
            baudrate=rtcm_baudrate,
            enabled=rtcm_enabled,
        )
        rtcm_injector = RtcmInjector(enabled=rtcm_enabled)
        rtcm_logger = RtcmLogger(enabled=rtcm_enabled)
        logger.info(f"RTCM logger initialized (enabled={rtcm_enabled})")

        def send_rtcm_message(frame_data):
            try:
                mav_conn.send_to_system(1, frame_data)
                rtcm_logger.log_injected(frame_data)
                logger.debug(f"RTCM frame sent to system 1: {len(frame_data)} bytes")
            except Exception as e:
                logger.error(f"Failed to send RTCM frame: {e}")

        rtcm_injector.set_send_callback(send_rtcm_message)

        # Queue ポーリングスレッド: serial → inject
        def _rtcm_poll_loop():
            while rtcm_serial_reader.running:
                try:
                    rtcm_frame = rtcm_serial_reader.queue.get(timeout=0.1)
                    rtcm_logger.log_raw(rtcm_frame)
                    rtcm_injector.inject(rtcm_frame)
                except Exception:
                    pass  # timeout or queue empty

        rtcm_serial_reader.start()
        threading.Thread(target=_rtcm_poll_loop, daemon=True).start()

        # RTCM統計を60秒ごとに表示するスレッド
        def rtcm_stats_printer():
            while rtcm_serial_reader.running:
                time.sleep(60)
                rtcm_logger.print_stats()

        threading.Thread(target=rtcm_stats_printer, daemon=True).start()

        from PySide6.QtWidgets import QApplication
        from ui.main_window import MainWindow

        app = QApplication(sys.argv)
        window = MainWindow(telemetry_store, dispatcher=dispatcher, connection=mav_conn, rtcm_reader=rtcm_serial_reader)
        window.show()

        logger.info("GUIイベントループを開始します。")
        exit_code = app.exec()

        logger.info("終了処理中...")
        router.stop()
        mav_conn.stop()
        rtcm_serial_reader.stop()
        rtcm_logger.print_stats()
        rtcm_logger.close()
        logger.info("RTCM injection stopped.")
        sys.exit(exit_code)

    else:
        # =====================================================================
        #  Default: Web Server mode (FastAPI)
        # =====================================================================
        from rtk_tools.config_loader import load_config
        config = load_config()
        srv_cfg = config.get("server", {})
        host = args.host or srv_cfg.get("host", "0.0.0.0")
        port = args.port or srv_cfg.get("port", 8000)
        logger.info(f"GCS Webサーバーを起動します: {host}:{port}")

        import uvicorn
        uvicorn.run(
            "app.server:app",
            host=host,
            port=port,
            log_level="info",
            reload=False,
        )
