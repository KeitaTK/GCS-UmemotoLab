"""app/api/routes.py — REST API endpoints for command dispatch."""

import logging, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("api.routes")
router = APIRouter(prefix="/api", tags=["commands"])

_telemetry_store = None
_dispatcher = None
_connection = None


def _get_ts():
    global _telemetry_store
    if _telemetry_store is None:
        from api.server import telemetry_store
        _telemetry_store = telemetry_store
    if _telemetry_store is None:
        raise HTTPException(status_code=503, detail="Backend not initialized (telemetry_store)")
    return _telemetry_store


def _get_disp():
    global _dispatcher
    if _dispatcher is None:
        from api.server import dispatcher
        _dispatcher = dispatcher
    if _dispatcher is None:
        raise HTTPException(status_code=503, detail="Backend not initialized (dispatcher)")
    return _dispatcher


def _get_conn():
    global _connection
    if _connection is None:
        from api.server import connection
        _connection = connection
    if _connection is None:
        raise HTTPException(status_code=503, detail="Backend not initialized (connection)")
    return _connection


# ==========================================================================
# Pydantic request models
# ==========================================================================

class SystemIdsRequest(BaseModel):
    system_ids: list[int] = Field(..., min_length=1)
    component_id: int = Field(default=1)


class ForceArmRequest(SystemIdsRequest):
    confirmed: bool = Field(..., description="Must be true to proceed")


class TakeoffRequest(SystemIdsRequest):
    altitude: float = Field(default=2.0, ge=0.5, le=500.0)


class LandRequest(SystemIdsRequest):
    descent_rate: float = Field(default=0.5, ge=0.0, le=20.0)


class GuidedPositionRequest(SystemIdsRequest):
    north: float = Field(default=0.0)
    east: float = Field(default=0.0)
    down: float = Field(default=-5.0)
    yaw: float = Field(default=0.0, ge=-180.0, le=180.0)


class GuidedVelocityRequest(SystemIdsRequest):
    vx: float = Field(default=0.0, ge=-20.0, le=20.0)
    vy: float = Field(default=0.0, ge=-20.0, le=20.0)
    vz: float = Field(default=0.0, ge=-20.0, le=20.0)
    yaw: float = Field(default=0.0, ge=-180.0, le=180.0)


# ==========================================================================
# Flight-mode decoding
# ==========================================================================

_COPTER_MODES = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO",
    4: "GUIDED", 5: "LOITER", 6: "RTH", 7: "CIRCLE",
    9: "LAND", 10: "OPTFLOW", 11: "POSHOLD", 13: "AUTO_TUNE",
    14: "SPORT", 16: "BRAKE", 17: "THROW", 18: "AVOID_ADSB",
    19: "GUIDED_NOGPS", 20: "SMART_RTL", 21: "FLOWHOLD",
    22: "FOLLOW", 23: "ZIGZAG", 24: "SYSTEMID",
    25: "AUTOROTATE", 26: "AUTO_RTL",
}


def _decode_mode(mode: int) -> str:
    return _COPTER_MODES.get(mode, f"MODE_{mode}")


# ==========================================================================
# GET /api/drones
# ==========================================================================

@router.get("/drones")
async def get_drones():
    ts = _get_ts()
    drones = []
    for sysid in ts.get_all_drone_ids():
        hb = ts.get_heartbeat(sysid)
        gps = ts.get_gps_raw(sysid)
        gpos = ts.get_global_position(sysid)
        ss = ts.get_sys_status(sysid)
        info = {
            "system_id": sysid, "armed": False, "mode": "UNKNOWN",
            "gps_fix": -1, "gps_sats": 0,
            "lat": None, "lon": None, "alt": None, "hdop": None,
            "battery_voltage": None, "battery_remaining": None,
        }
        if hb is not None:
            try:
                info["armed"] = (hb.base_mode & 0x80) != 0
            except Exception:
                pass
            try:
                info["mode"] = _decode_mode(int(hb.custom_mode))
            except Exception:
                pass
        if gps is not None:
            try:
                info["gps_fix"] = int(gps.fix_type)
                info["gps_sats"] = int(gps.satellites_visible)
                if gps.eph < 65535:
                    info["hdop"] = round(gps.eph / 100.0, 2)
            except Exception:
                pass
        if gpos is not None:
            try:
                info["lat"] = round(gpos.lat / 1e7, 7)
                info["lon"] = round(gpos.lon / 1e7, 7)
                info["alt"] = round(gpos.relative_alt / 1000.0, 2)
            except Exception:
                pass
        if ss is not None:
            try:
                info["battery_voltage"] = round(ss.voltage_battery / 1000.0, 2)
                info["battery_remaining"] = int(ss.battery_remaining)
            except Exception:
                pass
        drones.append(info)
    return {"status": "ok", "count": len(drones), "drones": drones}


# ==========================================================================
# GET /api/status
# ==========================================================================

@router.get("/status")
async def get_status():
    conn = _get_conn()
    try:
        conn_status = conn.get_connection_status()
    except Exception as e:
        logger.error("Failed to get connection status: %s", e)
        conn_status = {"is_connected": False, "error": str(e)}
    ts = _get_ts()
    drone_ids = ts.get_all_drone_ids() if ts else []
    return {
        "status": "ok",
        "server": {"uptime_seconds": round(time.monotonic(), 1)},
        "connection": {
            "is_connected": conn_status.get("is_connected", False),
            "type": conn_status.get("connection_type", "unknown"),
            "packets_received": conn_status.get("packet_received", 0),
            "packets_lost": conn_status.get("packet_loss", 0),
            "last_error": conn_status.get("last_error", None),
        },
        "drones_connected": len(drone_ids),
        "drone_ids": drone_ids,
    }


# ==========================================================================
# POST /api/arm
# ==========================================================================

@router.post("/arm")
async def cmd_arm(req: SystemIdsRequest):
    disp = _get_disp()
    for sysid in req.system_ids:
        logger.info("ARM → drone %d", sysid)
        disp.arm(sysid, component_id=req.component_id)
    return {"status": "ok", "command": "arm", "system_ids": req.system_ids}


# ==========================================================================
# POST /api/disarm
# ==========================================================================

@router.post("/disarm")
async def cmd_disarm(req: SystemIdsRequest):
    disp = _get_disp()
    for sysid in req.system_ids:
        logger.info("DISARM → drone %d", sysid)
        disp.disarm(sysid, component_id=req.component_id)
    return {"status": "ok", "command": "disarm", "system_ids": req.system_ids}


# ==========================================================================
# POST /api/force_arm
# ==========================================================================

@router.post("/force_arm")
async def cmd_force_arm(req: ForceArmRequest):
    if not req.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Force-arm requires 'confirmed: true'.",
        )
    disp = _get_disp()
    for sysid in req.system_ids:
        logger.warning("FORCE ARM → drone %d", sysid)
        disp.force_arm(sysid, component_id=req.component_id)
    return {
        "status": "ok", "command": "force_arm",
        "system_ids": req.system_ids,
        "warning": "Pre-arm checks disabled. Use restore_arm_params to re-enable.",
    }


# ==========================================================================
# POST /api/takeoff
# ==========================================================================

@router.post("/takeoff")
async def cmd_takeoff(req: TakeoffRequest):
    disp = _get_disp()
    ts = _get_ts()
    results = []
    for sysid in req.system_ids:
        hb = ts.get_heartbeat(sysid)
        armed = False
        if hb is not None:
            try:
                armed = (hb.base_mode & 0x80) != 0
            except Exception:
                pass
        if not armed:
            results.append({
                "system_id": sysid, "status": "skipped",
                "reason": "Drone is not armed. Arm first.",
            })
            continue
        logger.info("TAKEOFF → drone %d alt=%.1f", sysid, req.altitude)
        disp.takeoff(sysid, component_id=req.component_id, altitude=req.altitude)
        results.append({"system_id": sysid, "status": "sent"})
    all_ok = all(r["status"] == "sent" for r in results)
    return {
        "status": "ok" if all_ok else "partial",
        "command": "takeoff", "altitude": req.altitude, "results": results,
    }


# ==========================================================================
# POST /api/land
# ==========================================================================

@router.post("/land")
async def cmd_land(req: LandRequest):
    disp = _get_disp()
    for sysid in req.system_ids:
        logger.info("LAND → drone %d rate=%.1f", sysid, req.descent_rate)
        disp.land(sysid, component_id=req.component_id,
                  descent_rate=req.descent_rate)
    return {
        "status": "ok", "command": "land",
        "system_ids": req.system_ids, "descent_rate": req.descent_rate,
    }


# ==========================================================================
# POST /api/guided/position
# ==========================================================================

def _require_guided():
    disp = _get_disp()
    guided = getattr(disp, "guided", None)
    if guided is None:
        raise HTTPException(status_code=503, detail="Guided control unavailable")
    return guided


@router.post("/guided/position")
async def cmd_guided_position(req: GuidedPositionRequest):
    guided = _require_guided()
    for sysid in req.system_ids:
        logger.info("GUIDED POS → drone %d NED=(%.1f,%.1f,%.1f) yaw=%.1f",
                    sysid, req.north, req.east, req.down, req.yaw)
        guided.set_position_target_local_ned(
            sysid, req.component_id,
            x=req.north, y=req.east, z=req.down, yaw=req.yaw,
        )
    return {
        "status": "ok", "command": "guided_position",
        "system_ids": req.system_ids,
        "position": {"north": req.north, "east": req.east, "down": req.down},
        "yaw": req.yaw,
    }


# ==========================================================================
# POST /api/guided/velocity
# ==========================================================================

@router.post("/guided/velocity")
async def cmd_guided_velocity(req: GuidedVelocityRequest):
    guided = _require_guided()
    for sysid in req.system_ids:
        logger.info("GUIDED VEL → drone %d vel=(%.1f,%.1f,%.1f) yaw=%.1f",
                    sysid, req.vx, req.vy, req.vz, req.yaw)
        guided.set_velocity_target_local_ned(
            sysid, req.component_id,
            vx=req.vx, vy=req.vy, vz=req.vz, yaw=req.yaw,
        )
    return {
        "status": "ok", "command": "guided_velocity",
        "system_ids": req.system_ids,
        "velocity": {"vx": req.vx, "vy": req.vy, "vz": req.vz},
        "yaw": req.yaw,
    }
