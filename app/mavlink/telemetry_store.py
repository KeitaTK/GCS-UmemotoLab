# TelemetryStore: システムIDごとの状態管理
import threading

class TelemetryStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    def update(self, system_id, message_type, payload):
        with self._lock:
            if system_id not in self._data:
                self._data[system_id] = {}
            self._data[system_id][message_type] = payload

    def get(self, system_id, message_type=None):
        with self._lock:
            if system_id not in self._data:
                return None
            if message_type:
                return self._data[system_id].get(message_type)
            return self._data[system_id]

    def get_all(self):
        with self._lock:
            return dict(self._data)
