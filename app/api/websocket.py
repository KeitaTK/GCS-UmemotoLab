"""
WebSocket endpoint for real-time telemetry broadcast.

Broadcasts to all connected clients at 1Hz:
- connection: MavlinkConnection status (is_connected, packet stats, error)
- system_state: armed/mode from HEARTBEAT
- battery: voltage, current, remaining from SYS_STATUS
- gps: fix_type, satellites, lat/lon/alt, hdop
- command_state: pending count, last ACK status
- rtk: RtcmReader statistics
"""

import asyncio
import json
import logging
import time
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("api.websocket")

router = APIRouter()

# ── Client management ──────────────────────────────────────────────────
_active_clients: Set[WebSocket] = set()


# ── WebSocket endpoint ─────────────────────────────────────────────────

@router.websocket("/ws/telemetry")
async def telemetry_websocket(ws: WebSocket):
    """Enhanced telemetry WebSocket endpoint.

    Clients receive a JSON payload every second containing:
    connection, drones[system_id]{heartbeat, battery, gps, system_state, command_state}, rtk
    """
    await ws.accept()
    _active_clients.add(ws)
    logger.info(f"WS client connected (telemetry). Total: {len(_active_clients)}")

    try:
        while True:
            # Receive loop: accept client pings / configuration requests
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=1.0)
                logger.debug(f"WS message: {data}")
            except asyncio.TimeoutError:
                pass  # Normal polling timeout
    except WebSocketDisconnect:
        logger.info("WS client disconnected (telemetry)")
    except Exception as e:
        logger.error(f"WS error: {e}")
    finally:
        _active_clients.discard(ws)
        logger.info(f"WS client removed. Total: {len(_active_clients)}")


# ── Broadcast coroutine ────────────────────────────────────────────────

async def broadcast_loop():
    """Every 1 second, build telemetry payload and send to all _active_clients."""
    global _active_clients
    # Imported lazily so they are set by api.server.init_api() at startup
    from api.server import telemetry_store, connection, dispatcher, rtcm_reader

    while True:
        await asyncio.sleep(1.0)

        if not _active_clients:
            continue

        try:
            payload = _build_payload(telemetry_store, connection, dispatcher, rtcm_reader)
            if payload is None:
                continue

            text = json.dumps(payload, default=str)

            dead: Set[WebSocket] = set()
            for ws in _active_clients:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.add(ws)

            _active_clients -= dead

        except Exception as e:
            logger.error(f"Broadcast error: {e}", exc_info=True)


# ── Payload builder ────────────────────────────────────────────────────

_FIX_NAMES = {
    0: "NO_GPS", 1: "NO_FIX", 2: "2D_FIX", 3: "3D_FIX",
    4: "DGPS", 5: "RTK_FLOAT", 6: "RTK_FIXED",
    7: "STATIC", 8: "PPP",
}

_COPTER_MODES = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO",
    4: "GUIDED", 5: "LOITER", 6: "RTH", 7: "CIRCLE",
    9: "LAND", 10: "OPTFLOW", 11: "POSHOLD", 13: "AUTO_TUNE",
    14: "SPORT", 16: "BRAKE", 17: "THROW", 18: "AVOID_ADSB",
    19: "GUIDED_NOGPS", 20: "SMART_RTL", 21: "FLOWHOLD",
    22: "FOLLOW", 23: "ZIGZAG", 24: "SYSTEMID",
    25: "AUTOROTATE", 26: "AUTO_RTL",
}


def _build_payload(telemetry_store, connection, dispatcher, rtcm_reader) -> dict | None:
    """Build the complete telemetry payload for broadcast."""
    if telemetry_store is None:
        return None

    t_now = time.time()

    payload: dict = {
        "type": "telemetry",
        "timestamp": t_now,
        "connection": _build_connection_status(connection),
        "drones": {},
        "rtk": _build_rtk_status(rtcm_reader),
    }

    for sysid in sorted(telemetry_store.get_all_drone_ids()):
        drone: dict = {
            "heartbeat": _build_heartbeat(telemetry_store, sysid),
            "battery": _build_battery(telemetry_store, sysid),
            "gps": _build_gps(telemetry_store, sysid),
            "system_state": _build_system_state(telemetry_store, sysid),
            "command_state": _build_command_state(dispatcher, sysid),
        }
        payload["drones"][str(sysid)] = drone

    return payload


def _build_connection_status(connection) -> dict:
    if connection is None:
        return {"is_connected": False, "type": "unknown"}
    try:
        status = connection.get_connection_status()
        return {
            "is_connected": status.get("is_connected", False),
            "type": status.get("connection_type", "unknown"),
            "packets_received": status.get("packet_received", 0),
            "packet_loss": status.get("packet_loss", 0),
            "last_error": str(status.get("last_error", "")) or None,
        }
    except Exception:
        return {"is_connected": False, "type": "error"}


def _build_heartbeat(store, sysid: int) -> dict:
    hb = store.get_heartbeat(sysid)
    if hb is None:
        return {"armed": False, "mode": "N/A", "base_mode": 0, "custom_mode": -1}
    try:
        armed = (hb.base_mode & 0x80) != 0
        custom_mode = hb.custom_mode
        return {
            "armed": armed,
            "mode": _COPTER_MODES.get(custom_mode, f"MODE_{custom_mode}"),
            "base_mode": hb.base_mode,
            "custom_mode": custom_mode,
        }
    except Exception:
        return {"armed": False, "mode": "ERR", "base_mode": 0, "custom_mode": -1}


def _build_battery(store, sysid: int) -> dict:
    ss = store.get_sys_status(sysid)
    if ss is None:
        return {"voltage": None, "current": None, "remaining": None}
    try:
        voltage = ss.voltage_battery / 1000.0
        current = ss.current_battery / 100.0
        remaining = ss.battery_remaining if ss.battery_remaining >= 0 else None
        return {
            "voltage": round(voltage, 2),
            "current": round(current, 2),
            "remaining": remaining,
        }
    except Exception:
        return {"voltage": None, "current": None, "remaining": None}


def _build_gps(store, sysid: int) -> dict:
    gps_raw = store.get_gps_raw(sysid)
    gpos = store.get_global_position(sysid)

    result: dict = {
        "fix_type": -1,
        "fix_name": "N/A",
        "satellites": 0,
        "lat": None,
        "lon": None,
        "alt": None,
        "hdop": None,
    }

    if gps_raw is not None:
        try:
            fix_type = gps_raw.fix_type
            result["fix_type"] = fix_type
            result["fix_name"] = _FIX_NAMES.get(fix_type, f"UNKNOWN({fix_type})")
            result["satellites"] = gps_raw.satellites_visible
            eph = gps_raw.eph
            result["hdop"] = round(eph / 100.0, 2) if eph < 65535 else None
        except Exception:
            pass

    if gpos is not None:
        try:
            result["lat"] = round(gpos.lat / 1e7, 7)
            result["lon"] = round(gpos.lon / 1e7, 7)
            result["alt"] = round(gpos.alt / 1000.0, 2)
        except Exception:
            pass

    return result


def _build_system_state(store, sysid: int) -> dict:
    """Alias for heartbeat (armed + mode)."""
    return _build_heartbeat(store, sysid)


def _build_command_state(dispatcher, sysid: int) -> dict:
    if dispatcher is None:
        return {"pending_count": 0, "last_ack": None}

    try:
        pending = dispatcher.get_pending_commands(sysid)
    except Exception:
        return {"pending_count": 0, "last_ack": None}

    last_ack = None
    for cmd in reversed(pending):
        if cmd.get("status") in ("acked", "failed", "timeout"):
            last_ack = {
                "command": cmd.get("description", ""),
                "status": cmd["status"],
            }
            break

    return {
        "pending_count": len(pending),
        "last_ack": last_ack,
    }


def _build_rtk_status(rtcm_reader) -> dict:
    if rtcm_reader is None:
        return {"enabled": False, "messages_received": 0, "connections": 0, "reconnects": 0}
    try:
        stats = getattr(rtcm_reader, "stats", {})
        return {
            "enabled": getattr(rtcm_reader, "enabled", False),
            "messages_received": stats.get("messages_received", 0),
            "connections": stats.get("connections", 0),
            "reconnects": stats.get("reconnects", 0),
        }
    except Exception:
        return {"enabled": False, "messages_received": 0, "connections": 0, "reconnects": 0}
