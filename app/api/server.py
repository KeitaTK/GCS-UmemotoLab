"""
GCS-UmemotoLab Web API Server

FastAPI + WebSocket で GCS バックエンドを提供。
- REST API: テレメトリ取得、ドローン一覧、コマンド送信
- WebSocket: リアルタイムテレメトリプッシュ
"""
import asyncio
import json
import logging
import threading
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

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


# === コマンド API ===

class CommandRequest(BaseModel):
    system_ids: list[int] = Field(..., description="対象ドローンの System ID リスト")
    component_id: int = Field(default=1, description="コンポーネント ID")


class TakeoffRequest(CommandRequest):
    altitude: float = Field(default=2.0, description="離陸高度 (m)")


class LandRequest(CommandRequest):
    descent_rate: float = Field(default=0.5, description="降下速度 (m/s)")


class GuidedPositionRequest(CommandRequest):
    north: float = Field(default=0.0, description="北方向位置 (m)")
    east: float = Field(default=0.0, description="東方向位置 (m)")
    down: float = Field(default=-5.0, description="下方向位置 (m)")
    yaw: float = Field(default=0.0, description="ヨー角 (deg)")


class GuidedVelocityRequest(CommandRequest):
    vx: float = Field(default=0.0, description="X速度 (m/s)")
    vy: float = Field(default=0.0, description="Y速度 (m/s)")
    vz: float = Field(default=0.0, description="Z速度 (m/s)")
    yaw: float = Field(default=0.0, description="ヨー角 (deg)")


@app.post("/api/command/arm")
async def cmd_arm(req: CommandRequest):
    """Arm コマンド"""
    if dispatcher is None:
        return JSONResponse({"error": "Backend not initialized"}, status_code=503)
    for sysid in req.system_ids:
        logger.info(f"ARM command -> drone {sysid}")
        dispatcher.arm(sysid, component_id=req.component_id)
    return {"status": "sent", "command": "arm", "system_ids": req.system_ids}


@app.post("/api/command/disarm")
async def cmd_disarm(req: CommandRequest):
    """Disarm コマンド"""
    if dispatcher is None:
        return JSONResponse({"error": "Backend not initialized"}, status_code=503)
    for sysid in req.system_ids:
        logger.info(f"DISARM command -> drone {sysid}")
        dispatcher.disarm(sysid, component_id=req.component_id)
    return {"status": "sent", "command": "disarm", "system_ids": req.system_ids}


@app.post("/api/command/force_arm")
async def cmd_force_arm(req: CommandRequest):
    """Force Arm コマンド（プリチェック無効化、屋内テスト用）"""
    if dispatcher is None:
        return JSONResponse({"error": "Backend not initialized"}, status_code=503)
    for sysid in req.system_ids:
        logger.warning(f"FORCE ARM command -> drone {sysid}")
        dispatcher.force_arm(sysid, component_id=req.component_id)
    return {"status": "sent", "command": "force_arm", "system_ids": req.system_ids, "warning": "Force arm: pre-arm checks disabled"}


@app.post("/api/command/restore_arm_params")
async def cmd_restore_arm_params(req: CommandRequest):
    """Force Arm で無効化したパラメータを復元"""
    if dispatcher is None:
        return JSONResponse({"error": "Backend not initialized"}, status_code=503)
    for sysid in req.system_ids:
        logger.info(f"Restoring arm params -> drone {sysid}")
        dispatcher.restore_arm_params(sysid, component_id=req.component_id)
    return {"status": "sent", "command": "restore_arm_params", "system_ids": req.system_ids}


@app.post("/api/command/takeoff")
async def cmd_takeoff(req: TakeoffRequest):
    """Takeoff コマンド"""
    if dispatcher is None:
        return JSONResponse({"error": "Backend not initialized"}, status_code=503)
    results = []
    for sysid in req.system_ids:
        hb = telemetry_store.get_heartbeat(sysid)
        armed = False
        if hb:
            try:
                armed = (hb.base_mode & 0x80) != 0
            except Exception:
                pass
        if not armed:
            results.append({"system_id": sysid, "status": "skipped", "reason": "Not armed"})
            continue
        logger.info(f"TAKEOFF command -> drone {sysid} at {req.altitude}m")
        dispatcher.takeoff(sysid, component_id=req.component_id, altitude=req.altitude)
        results.append({"system_id": sysid, "status": "sent"})
    return {"status": "sent", "command": "takeoff", "results": results}


@app.post("/api/command/land")
async def cmd_land(req: LandRequest):
    """Land コマンド"""
    if dispatcher is None:
        return JSONResponse({"error": "Backend not initialized"}, status_code=503)
    for sysid in req.system_ids:
        logger.info(f"LAND command -> drone {sysid}")
        dispatcher.land(sysid, component_id=req.component_id, descent_rate=req.descent_rate)
    return {"status": "sent", "command": "land", "system_ids": req.system_ids}


@app.post("/api/command/guided_position")
async def cmd_guided_position(req: GuidedPositionRequest):
    """Guided Position コマンド"""
    if dispatcher is None or not hasattr(dispatcher, 'guided') or dispatcher.guided is None:
        return JSONResponse({"error": "Guided control not available"}, status_code=503)
    for sysid in req.system_ids:
        logger.info(f"Guided position -> drone {sysid}: NED=({req.north},{req.east},{req.down}), yaw={req.yaw}")
        dispatcher.guided.set_position_target_local_ned(
            sysid, req.component_id, req.north, req.east, req.down, yaw=req.yaw
        )
    return {"status": "sent", "command": "guided_position", "system_ids": req.system_ids}


@app.post("/api/command/guided_velocity")
async def cmd_guided_velocity(req: GuidedVelocityRequest):
    """Guided Velocity コマンド"""
    if dispatcher is None or not hasattr(dispatcher, 'guided') or dispatcher.guided is None:
        return JSONResponse({"error": "Guided control not available"}, status_code=503)
    for sysid in req.system_ids:
        logger.info(f"Guided velocity -> drone {sysid}: vel=({req.vx},{req.vy},{req.vz}), yaw={req.yaw}")
        dispatcher.guided.set_velocity_target_local_ned(
            sysid, req.component_id, req.vx, req.vy, req.vz, yaw=req.yaw
        )
    return {"status": "sent", "command": "guided_velocity", "system_ids": req.system_ids}


# === WebSocket: リアルタイムテレメトリプッシュ ===

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _active_ws.append(ws)
    logger.info(f"WebSocket client connected. Total: {len(_active_ws)}")

    try:
        while True:
            # クライアントからのメッセージを受信（ping/pong や設定変更用）
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=1.0)
                # 設定変更リクエスト等を処理可能
                logger.debug(f"WS received: {data}")
            except asyncio.TimeoutError:
                pass  # タイムアウトは正常（ポーリングのため）
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if ws in _active_ws:
            _active_ws.remove(ws)
        logger.info(f"WebSocket client removed. Total: {len(_active_ws)}")


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


# === Springy Fly: index.html ===
@app.get("/")
async def root():
    """GCS Web UI を提供"""
    try:
        with open("web/static/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        try:
            with open("app/web/index.html", "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(content="<h1>GCS-UmemotoLab API</h1><p>API is running. Web UI not found.</p>")