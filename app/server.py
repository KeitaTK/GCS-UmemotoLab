"""
GCS-UmemotoLab FastAPI Server Entry Point.

Startup:
  1. Initialize MavlinkConnection (UDP or Serial)
  2. Initialize MessageRouter + TelemetryStore + CommandDispatcher
  3. Initialize RtcmReader + RtcmInjector
  4. Request data streams from Pixhawk
  5. Start WebSocket broadcast loop (1 Hz)

Bind address: 100.95.30.60 (Tailscale)
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
import threading

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

# -- Import the existing FastAPI app from api.server ---------------------
from api.server import app, init_api, broadcast_telemetry

# -- Import the enhanced WebSocket router --------------------------------
from api.websocket import router as ws_router, broadcast_loop

# -- Import the REST API command router ----------------------------------
from api.routes import router as cmd_router

# -- CORS middleware (allow Tailscale + local access) ---------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Static files mount --------------------------------------------------
try:
    app.mount("/static", StaticFiles(directory="web/static"), name="static")
except RuntimeError:
    pass  # Already mounted or directory missing at import time

# -- WebSocket router ----------------------------------------------------
app.include_router(ws_router)

# -- REST API command router ---------------------------------------------
app.include_router(cmd_router)

logger = logging.getLogger("server")


# =========================================================================
#  Startup / Shutdown lifecycle
# =========================================================================

@app.on_event("startup")
async def on_startup():
    """Initialize all backend components."""
    from logging_config import setup_logging
    setup_logging()
    global logger
    logger = logging.getLogger("server")
    logger.info("=== GCS Web Server starting ===")

    # ── Imports ────────────────────────────────────────────────────────
    from rtk_tools.config_loader import resolve_config_path
    from mavlink.connection import MavlinkConnection
    from mavlink.message_router import MessageRouter
    from rtk_tools.telemetry_store import TelemetryStore
    from rtk_tools.command_dispatcher import CommandDispatcher
    from rtk_tools.guided_control import GuidedControl
    from rtk_tools.rtcm_reader import RtcmReader
    from rtk_tools.rtcm_injector import RtcmInjector

    # ── Config ─────────────────────────────────────────────────────────
    config_path = resolve_config_path()
    logger.info(f"Config: {config_path}")

    # ── Core backend ───────────────────────────────────────────────────
    telemetry_store = TelemetryStore()
    mav_conn = MavlinkConnection(config_path)

    dispatcher = CommandDispatcher(mav_conn)
    dispatcher.guided = GuidedControl(mav_conn)

    router = MessageRouter(mav_conn, telemetry_store, command_dispatcher=dispatcher)
    router.start()

    # ── Request data streams (after connection stabilizes) ─────────────
    def _request_streams():
        import time as _time
        logger.info("Waiting for Pixhawk connection to stabilize...")
        _time.sleep(2.0)
        try:
            msg = mav_conn.mav.request_data_stream_encode(
                1, 0,  # target_system, target_component
                0,     # req_stream_id (all)
                5,     # req_message_rate (5 Hz)
                1,     # start_stop (start)
            )
            frame = msg.pack(mav_conn.mav)
            mav_conn.send(1, frame)
            logger.info("Data stream request sent")
        except Exception as e:
            logger.error(f"Stream request failed: {e}")

    threading.Thread(target=_request_streams, daemon=True).start()

    # ── RTCM / RTK ─────────────────────────────────────────────────────
    rtcm_enabled = mav_conn.config.get("rtcm_enabled", True)
    rtcm_host = mav_conn.config.get("rtcm_host", "127.0.0.1")
    rtcm_port = mav_conn.config.get("rtcm_tcp_port", 15000)

    rtcm_reader = RtcmReader(host=rtcm_host, port=rtcm_port, enabled=rtcm_enabled)
    rtcm_injector = RtcmInjector(enabled=rtcm_enabled)

    def _send_rtcm_frame(frame_data):
        try:
            mav_conn.send_to_system(1, frame_data)
            mav_conn.send_to_system(2, frame_data)
        except Exception as e:
            logger.error(f"RTCM send failed: {e}")

    rtcm_injector.set_send_callback(_send_rtcm_frame)
    rtcm_reader.register_callback(lambda data: rtcm_injector.inject(data))
    rtcm_reader.start()

    # ── Wire API globals ───────────────────────────────────────────────
    init_api(telemetry_store, dispatcher, mav_conn, rtcm_reader)

    # ── Store references for shutdown ──────────────────────────────────
    app.state.mav_conn = mav_conn
    app.state.router = router
    app.state.rtcm_reader = rtcm_reader

    # ── Start telemetry broadcast loops ────────────────────────────────
    asyncio.create_task(broadcast_telemetry())   # existing 0.5s loop
    asyncio.create_task(broadcast_loop())         # enhanced 1s loop

    logger.info("=== GCS Web Server started (100.95.30.60:8000) ===")


@app.on_event("shutdown")
async def on_shutdown():
    """Cleanup all components."""
    logger.info("Shutting down...")

    if hasattr(app.state, "router"):
        app.state.router.stop()
    if hasattr(app.state, "mav_conn"):
        app.state.mav_conn.stop()
    if hasattr(app.state, "rtcm_reader"):
        app.state.rtcm_reader.stop()

    logger.info("=== Server shutdown complete ===")


# =========================================================================
#  Main
# =========================================================================

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="100.95.30.60",
        port=8000,
        log_level="info",
        reload=False,
    )
