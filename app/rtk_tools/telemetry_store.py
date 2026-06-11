# TelemetryStore: システムIDごとの状態管理
import threading
import time

class TelemetryStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    def update(self, system_id, message_type, payload):
        with self._lock:
            if system_id not in self._data:
                self._data[system_id] = {}
            self._data[system_id][message_type] = payload

            if message_type == 'NAMED_VALUE_FLOAT':
                field_name = getattr(payload, 'name', 'unknown')
                if isinstance(field_name, bytes):
                    field_name = field_name.decode('utf-8', errors='ignore')
                field_name = str(field_name)
                value = getattr(payload, 'value', 0.0)
                timestamp = getattr(payload, 'time_usec', 0)
                if not timestamp:
                    timestamp = int(time.time() * 1_000_000)

                nvf_history = self._data[system_id].setdefault('NAMED_VALUE_FLOAT_HISTORY', {})
                field_history = nvf_history.setdefault(field_name, [])
                field_history.append({
                    'value': value,
                    'timestamp': timestamp,
                    'payload': payload,
                })

                self._data[system_id].setdefault('NAMED_VALUE_FLOAT_BY_NAME', {})[field_name] = payload

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
    
    def get_all_drone_ids(self):
        """Get list of all active drone system IDs"""
        with self._lock:
            return list(self._data.keys())
    
    def get_heartbeat(self, system_id):
        """Get HEARTBEAT message for a drone"""
        with self._lock:
            if system_id in self._data:
                return self._data[system_id].get('HEARTBEAT')
            return None
    
    def get_sys_status(self, system_id):
        """Get SYS_STATUS message for a drone (battery, GPS, etc.)"""
        with self._lock:
            if system_id in self._data:
                return self._data[system_id].get('SYS_STATUS')
            return None
    
    def get_gps_raw(self, system_id):
        """Get GPS_RAW_INT message for a drone (fix_type, satellites, hdop, etc.)"""
        with self._lock:
            if system_id in self._data:
                return self._data[system_id].get('GPS_RAW_INT')
            return None
    
    def get_global_position(self, system_id):
        """Get GLOBAL_POSITION_INT message for a drone (GPS coordinates)"""
        with self._lock:
            if system_id in self._data:
                return self._data[system_id].get('GLOBAL_POSITION_INT')
            return None

    def get_named_value_float_history(self, system_id):
        """Get NAMED_VALUE_FLOAT history grouped by field name."""
        with self._lock:
            if system_id in self._data:
                history = self._data[system_id].get('NAMED_VALUE_FLOAT_HISTORY', {})
                return {field: list(entries) for field, entries in history.items()}
            return {}

    def get_named_value_float_latest(self, system_id):
        """Get the latest NAMED_VALUE_FLOAT values by field name."""
        with self._lock:
            if system_id in self._data:
                latest = self._data[system_id].get('NAMED_VALUE_FLOAT_BY_NAME', {})
                return dict(latest)
            return {}

