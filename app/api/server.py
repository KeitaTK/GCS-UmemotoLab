"""
GCS-UmemotoLab Web API Server

FastAPI アプリケーション定義。静的エンドポイントはここで定義。
- REST API: ヘルスチェック、ドローン一覧、テレメトリ取得
- コマンド系と接続管理は api/routes.py に移譲
- WebSocket は api/websocket.py に移譲
"""
import asyncio
import json
import logging
import os

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("api.server")

# === FastAPI アプリケーション ===
app = FastAPI(title="GCS-UmemotoLab API", version="2.0.0")

# === グローバル参照（main.py から注入） ===
telemetry_store = None
dispatcher = None
connection = None
rtcm_reader = None

# === WebSocket 接続管理 ===
_active_ws: list[WebSocket] = []


def init_api(_telemetry_store, _dispatcher, _connection, _rtcm_reader=None):
    """Initialize API with backend components."""
    global telemetry_store, dispatcher, connection, rtcm_reader
    telemetry_store = _telemetry_store
    dispatcher = _dispatcher
    connection = _connection
    rtcm_reader = _rtcm_reader
    logger.info("API initialized with backend components.")


# === ヘルパー：MAVLinkメッセージ → JSON ===
def _msg_to_dict(msg) -> dict:
    """pymavlink メッセージを辞書に変換"""
    if msg is None:
        return {}
    try:
        return msg.to_dict()
    except AttributeError:
        return {"_raw": str(msg)}


def _serialize_telemetry(system_id: int) -> dict:
    """指定 system_id の全テレメトリをシリアライズ"""
    data = telemetry_store.get(system_id)
    if data is None:
        return {"system_id": system_id, "telemetry": {}}

    result = {"system_id": system_id, "telemetry": {}}
    for msg_type, payload in data.items():
        if msg_type in ("NAMED_VALUE_FLOAT_HISTORY", "NAMED_VALUE_FLOAT_BY_NAME"):
            continue
        result["telemetry"][msg_type] = _msg_to_dict(payload)

    return result

# === REST API エンドポイント ===

@app.get("/api/health")
async def health():
    """ヘルスチェック"""
    return {
        "status": "ok",
        "drones": telemetry_store.get_all_drone_ids() if telemetry_store else [],
    }


@app.get("/api/drones")
async def get_drones():
    """全ドローン一覧（システムID + 基本情報）"""
    if telemetry_store is None:
        return JSONResponse({"error": "Backend not initialized"}, status_code=503)

    drones = []
    for sysid in telemetry_store.get_all_drone_ids():
        hb = telemetry_store.get_heartbeat(sysid)
        gps = telemetry_store.get_gps_raw(sysid)
        gpos = telemetry_store.get_global_position(sysid)
        sys_status = telemetry_store.get_sys_status(sysid)

        drone_info = {
            "system_id": sysid,
            "armed": False,
            "mode": "UNKNOWN",
            "gps_fix": -1,
            "gps_sats": 0,
            "lat": None,
            "lon": None,
            "alt": None,
            "hdop": None,
            "battery_voltage": None,
            "battery_remaining": None,
        }

        if hb:
            try:
                drone_info["armed"] = (hb.base_mode & 0x80) != 0
            except Exception:
                pass
            try:
                mode = hb.custom_mode
                drone_info["mode"] = _decode_flight_mode(mode)
            except Exception:
                pass

        if gps:
            try:
                drone_info["gps_fix"] = gps.fix_type
                drone_info["gps_sats"] = gps.satellites_visible
                drone_info["hdop"] = round(gps.eph / 100.0, 2) if gps.eph < 65535 else None
            except Exception:
                pass

        if gpos:
            try:
                drone_info["lat"] = round(gpos.lat / 1e7, 7)
                drone_info["lon"] = round(gpos.lon / 1e7, 7)
                drone_info["alt"] = round(gpos.relative_alt / 1000.0, 2)
            except Exception:
                pass

        if sys_status:
            try:
                drone_info["battery_voltage"] = round(sys_status.voltage_battery / 1000.0, 2)
                drone_info["battery_remaining"] = sys_status.battery_remaining
            except Exception:
                pass

        drones.append(drone_info)

    return {"drones": drones}


@app.get("/api/telemetry/{system_id}")
async def get_telemetry(system_id: int):
    """特定ドローンの全テレメトリ"""
    if telemetry_store is None:
        return JSONResponse({"error": "Backend not initialized"}, status_code=503)
    return _serialize_telemetry(system_id)


@app.get("/api/telemetry/{system_id}/{msg_type}")
async def get_telemetry_by_type(system_id: int, msg_type: str):
    """特定ドローンの特定メッセージタイプのテレメトリ"""
    if telemetry_store is None:
        return JSONResponse({"error": "Backend not initialized"}, status_code=503)

    data = telemetry_store.get(system_id, msg_type)
    if data is None:
        return JSONResponse({"error": f"No data for system_id={system_id}, type={msg_type}"}, status_code=404)

    return {
        "system_id": system_id,
        "message_type": msg_type,
        "data": _msg_to_dict(data),
    }


async def broadcast_telemetry():
    """定期的に全 WebSocket クライアントへテレメトリをブロードキャスト"""
    while True:
        await asyncio.sleep(0.5)  # 2Hz でプッシュ
        if not _active_ws or telemetry_store is None:
            continue

        try:
            # 全ドローンのテレメトリを収集
            drones_data = []
            for sysid in telemetry_store.get_all_drone_ids():
                drones_data.append(_serialize_telemetry(system_id=sysid))

            payload = json.dumps({"type": "telemetry", "drones": drones_data}, default=str)

            # 全クライアントにブロードキャスト
            disconnected = []
            for ws in _active_ws:
                try:
                    await ws.send_text(payload)
                except Exception:
                    disconnected.append(ws)

            for ws in disconnected:
                if ws in _active_ws:
                    _active_ws.remove(ws)

        except Exception as e:
            logger.error(f"Broadcast error: {e}")


# === フライトモードデコード ===
_COPTER_MODES = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO",
    4: "GUIDED", 5: "LOITER", 6: "RTH", 7: "CIRCLE",
    9: "LAND", 10: "OPTFLOW", 11: "POSHOLD", 13: "AUTO_TUNE",
    14: "SPORT", 16: "BRAKE", 17: "THROW", 18: "AVOID_ADSB",
    19: "GUIDED_NOGPS", 20: "SMART_RTL", 21: "FLOWHOLD",
    22: "FOLLOW", 23: "ZIGZAG", 24: "SYSTEMID",
    25: "AUTOROTATE", 26: "AUTO_RTL",
}


def _decode_flight_mode(mode: int) -> str:
    """カスタムモードを文字列にデコード"""
    return _COPTER_MODES.get(mode, f"MODE_{mode}")


# === index.html ===
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@app.get("/")
async def root():
    """GCS Web UI を提供"""
    candidates = [
        os.path.join(_PROJECT_ROOT, "web", "static", "index.html"),
        os.path.join(_PROJECT_ROOT, "app", "web", "index.html"),
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except OSError:
            continue
    return HTMLResponse(content="<h1>GCS-UmemotoLab API</h1><p>API is running. Web UI not found.</p>")
