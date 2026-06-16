# main.py
import sys
import os
import subprocess
import socket
import signal
import atexit

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging
import logging

from rtk_tools.config_loader import resolve_config_path

from mavlink.connection import MavlinkConnection
from mavlink.message_router import MessageRouter
from rtk_tools.telemetry_store import TelemetryStore
from rtk_tools.rtcm_reader import RtcmReader
from rtk_tools.rtcm_injector import RtcmInjector
import threading
import time
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


# ── Tailscale SSH Tunnel 自動セットアップ ──────────────────────────

_tunnel_processes = []  # cleanup用


def _setup_tailscale_tunnel(config: dict, logger: logging.Logger):
    """SSHトンネル＋socat＋ブリッジを自動起動（Tailscale経由の実機接続用）。

    UDP直結ができないTailscale環境で、TCPベースのリレーを構築する。
    失敗してもエラーをログに残すだけで GCS の起動は続行する。
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # トンネルが必要か判定: endpoint が 127.0.0.1 で始まる場合
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

    # 1) Raspi 側 socat 起動 (TCP:14551 → UDP:14550 → mavlink-router)
    logger.info(f"[1/3] Raspi socat起動: TCP:{raspi_tcp_port}→UDP:14550")
    try:
        subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", ssh_host,
             f"ss -tlnp | grep -q ':{raspi_tcp_port}' || "
             f"socat TCP-LISTEN:{raspi_tcp_port},fork,reuseaddr UDP:localhost:14550 &"],
            timeout=12, capture_output=True
        )
        logger.info("  → Raspi socat 起動完了")
    except subprocess.TimeoutExpired:
        logger.warning("  → Raspi socat SSH タイムアウト（モバイル回線遅延、既存 socat を利用）")
    except Exception as e:
        logger.warning(f"  → Raspi socat 起動失敗: {e}")

    # 2) SSH トンネル確立 (Mac:14551 → Raspi:14551)
    logger.info(f"[2/3] SSHトンネル確立: localhost:{local_tcp_port}→{ssh_host}:{raspi_tcp_port}")
    try:
        proc = subprocess.Popen(
            ["ssh", "-N", "-L", f"{local_tcp_port}:localhost:{raspi_tcp_port}",
             "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30",
             "-o", "ExitOnForwardFailure=yes", ssh_host],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
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
        proc = subprocess.Popen(
            [sys.executable, bridge_script,
             str(bridge_udp_port), str(local_tcp_port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        _tunnel_processes.append(proc)
        time.sleep(1)
        logger.info("  → ローカルブリッジ起動完了")
    except Exception as e:
        logger.warning(f"  → ブリッジ起動失敗: {e}")

    logger.info("=== Tailscale SSHトンネル自動セットアップ完了 ===")


def _cleanup_tunnel():
    """終了時にトンネルプロセスを停止"""
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
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("GCSアプリケーションが起動しました。")

    # 設定ファイルパス
    config_path = resolve_config_path()
    logger.info(f"設定ファイルを使用します: {config_path}")
    telemetry_store = TelemetryStore()

    # ── Tailscale SSHトンネル自動セットアップ ──
    import yaml
    with open(config_path, 'r') as f:
        raw_config = yaml.safe_load(f)
    _setup_tailscale_tunnel(raw_config, logger)
    atexit.register(_cleanup_tunnel)

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
