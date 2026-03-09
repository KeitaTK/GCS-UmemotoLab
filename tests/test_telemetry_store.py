import pytest
from app.mavlink.telemetry_store import TelemetryStore

def test_telemetry_store_initial_state():
    store = TelemetryStore()
    assert store.get_all() == {}
    assert store.get(1) is None

def test_telemetry_store_update_and_get():
    store = TelemetryStore()
    # Mock data for HEARTBEAT
    payload = {"type": 1, "autopilot": 3, "base_mode": 81, "system_status": 4}
    
    store.update(system_id=1, message_type="HEARTBEAT", payload=payload)
    
    expected_data = {"HEARTBEAT": payload}
    assert store.get(1) == expected_data
    assert store.get(1, "HEARTBEAT") == payload
    assert store.get(1, "SYS_STATUS") is None

def test_telemetry_store_multiple_systems():
    store = TelemetryStore()
    payload_1 = {"type": "QUADROTOR"}
    payload_2 = {"type": "HEXAROTOR"}
    
    store.update(1, "HEARTBEAT", payload_1)
    store.update(2, "HEARTBEAT", payload_2)
    
    all_data = store.get_all()
    assert len(all_data) == 2
    assert all_data[1]["HEARTBEAT"] == payload_1
    assert all_data[2]["HEARTBEAT"] == payload_2
