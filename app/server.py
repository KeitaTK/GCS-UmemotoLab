"""
GCS-UmemotoLab FastAPI Server Entry Point.

Startup (lightweight):
  1. Configure logging
  2. Start WebSocket broadcast loops (no-op until backend connected)

Backend components (MavlinkConnection, TelemetryStore, etc.) are initialized
on-demand via POST /api/connect and torn down via POST /api/disconnect.

Bind address: 100.95.30.60 (Tailscale)
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging

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
    """Lightweight startup: logging only. Backend initialized via /api/connect."""
    from logging_config import setup_logging
    setup_logging()
    global logger
    logger = logging.getLogger("server")
    logger.info("=== GCS Web Server starting (lightweight) ===")

    # Start broadcast loops immediately (they no-op when backend is None)
    asyncio.create_task(broadcast_telemetry())   # existing 0.5s loop
    asyncio.create_task(broadcast_loop())         # enhanced 1s loop

    logger.info("=== GCS Web Server started (100.95.30.60:8000) ===\n"
                "    Backend not connected. Use POST /api/connect to connect.")


@app.on_event("shutdown")
async def on_shutdown():
    """Cleanup all components."""
    logger.info("Shutting down...")

    if hasattr(app.state, "router"):
        try:
            app.state.router.stop()
        except Exception as e:
            logger.warning(f"router.stop() failed: {e}")
    if hasattr(app.state, "mav_conn"):
        try:
            app.state.mav_conn.stop()
        except Exception as e:
            logger.warning(f"mav_conn.stop() failed: {e}")
    if hasattr(app.state, "rtcm_reader"):
        try:
            app.state.rtcm_reader.stop()
        except Exception as e:
            logger.warning(f"rtcm_reader.stop() failed: {e}")

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
