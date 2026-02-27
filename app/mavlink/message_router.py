# MessageRouter: 受信ループとディスパッチ
import threading
import logging
from .telemetry_store import TelemetryStore

class MessageRouter:
    def __init__(self, mavlink_conn, telemetry_store):
        self.logger = logging.getLogger(__name__)
        self.mavlink_conn = mavlink_conn
        self.telemetry_store = telemetry_store
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.logger.info("MessageRouter受信ループ開始")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        self.logger.info("MessageRouter受信ループ停止")

    def _run(self):
        def callback(data, addr):
            # ここでMAVLinkパース処理を呼び出し、TelemetryStoreに格納
            # 仮実装: system_id=1, message_type='HEARTBEAT', payload=data
            self.telemetry_store.update(system_id=1, message_type='HEARTBEAT', payload=data)
        self.mavlink_conn.start(callback)
        while self.running:
            pass  # 受信はコールバックで処理
