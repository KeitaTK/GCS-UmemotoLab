"""app/api/base_station_routes.py — REST API for RTK Base Station (v2) control."""

import logging
import threading
import time
from argparse import Namespace

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("api.base_station")

router = APIRouter(prefix="/api/base_station", tags=["base_station"])

# ── Read base_station mode from config.yml ─────────────────────────────

def _get_bs_mode() -> str:
    """Read base_station mode from hardware config."""
    try:
        from rtk_tools.config_loader import load_hardware_config
        hw = load_hardware_config()
        return hw.get('base_station', {}).get('mode', 'manual')
    except Exception:
        return 'manual'


# ==========================================================================
# POST /api/base_station/start — Start RTK Base Station (async)
# ==========================================================================

@router.post("/start")
async def base_station_start(request: Request):
    """Start the RTK Base Station asynchronously.

    1. Returns immediately with status "starting".
    2. Background thread runs: config merge → F9P setup → serial reader → TCP server.
    3. auto mode: USB detect + 60s observation runs in background.
    """
    app = request.app

    # Check if already running or starting
    station = getattr(app.state, "base_station", None)
    phase = getattr(app.state, "bs_phase", "idle")
    if station is not None:
        return JSONResponse(
            {"status": "error", "detail": "Base station already running. Stop it first."},
            status_code=409,
        )
    if phase == "starting":
        return JSONResponse(
            {"status": "error", "detail": "Base station is already starting. Please wait."},
            status_code=409,
        )

    logger.info("=== RTK Base Station start requested (async) ===")

    # Set initial phase immediately
    app.state.bs_phase = "starting"
    app.state.bs_error = None
    app.state.base_station = None
    app.state.base_station_thread = None
    app.state.base_station_start_time = None

    bs_mode = _get_bs_mode()

    def _run_initialization(app_ref):
        """Background thread: build config, create station, start components."""
        try:
            from rtk_tools.rtk_base_station_v2 import (
                Config, RtkBaseStation,
            )
            from rtk_tools.standalone_obs import (
                StandaloneObserver, auto_detect_port, FIX_NAMES,
            )
            from rtk_tools.config_loader import load_hardware_config

            logger.info("[BS thread] Building config...")

            # 1. Read hardware config manually (replaces _merge_config to support progress callback)
            hw = load_hardware_config()
            bs = hw.get('base_station', {})
            bs_mode = bs.get('mode', 'manual')
            obs_duration = int(bs.get('auto_obs_duration', 60))

            config = Config()
            config.log_file = "rtk_base_station_web.log"
            config.save_to_flash = bs.get('save_to_flash', True)

            if 'f9p' in hw:
                config.serial_port = hw['f9p'].get('serial_port', config.serial_port)
                config.baudrate = hw['f9p'].get('baudrate', config.baudrate)
                config.f9p_baudrate = hw['f9p'].get('baudrate', config.f9p_baudrate)

            if 'forward' in hw:
                fwd = hw['forward']
                config.udp_broadcast_host = fwd.get('host', config.udp_broadcast_host)
                config.udp_broadcast_port = fwd.get('port', config.udp_broadcast_port)

            if bs_mode == 'auto':
                # Auto mode: USB detect + observation with progress callback
                logger.info("[BS thread] Auto mode: detecting USB port...")
                config.serial_port = auto_detect_port()

                # Run observation with progress callback
                def _on_progress(prog):
                    app_ref.state.bs_progress = prog
                    app_ref.state.bs_phase = "starting"

                logger.info(f"[BS thread] Observing position for {obs_duration}s...")
                observer = StandaloneObserver(
                    port=config.serial_port,
                    baudrate=config.baudrate,
                    duration_sec=obs_duration,
                    progress_callback=_on_progress,
                )
                observer.run()

                if observer.samples:
                    # Compute best-fix mean from observer results
                    from rtk_tools.standalone_obs import FIX_PRIORITY as FP
                    counts = {}
                    for s in observer.samples:
                        counts[s.fix_type] = counts.get(s.fix_type, 0) + 1
                    best_fix = max(counts.keys(), key=lambda ft: FP.get(ft, -1))
                    best_samples = [s for s in observer.samples if s.fix_type == best_fix]
                    if best_samples:
                        n = len(best_samples)
                        lats = [s.latitude for s in best_samples]
                        lons = [s.longitude for s in best_samples]
                        alts = [s.altitude for s in best_samples]
                        config.fixed_lat = sum(lats) / n
                        config.fixed_lon = sum(lons) / n
                        config.fixed_alt = sum(alts) / n
                        logger.info(f"[BS thread] Fixed position: {config.fixed_lat:.7f}, {config.fixed_lon:.7f}, {config.fixed_alt:.2f}m")
                    else:
                        raise RuntimeError("Auto observation failed: no samples with valid fix")
                else:
                    raise RuntimeError("Auto observation failed: no samples collected")
            else:
                # Manual mode
                config.serial_port = bs.get('serial_port', config.serial_port)
                config.fixed_lat = bs.get('fixed_lat')
                config.fixed_lon = bs.get('fixed_lon')
                config.fixed_alt = bs.get('fixed_alt')

            # 2. Create station instance
            logger.info("[BS thread] Creating RtkBaseStation instance...")
            station = RtkBaseStation(config)

            # 3. Start station (F9P config, serial reader, TCP server, etc.)
            logger.info("[BS thread] Starting station components...")
            station.start()

            # 4. Store on app.state (runs in main thread via timer)
            app_ref.state.base_station = station
            app_ref.state.base_station_thread = threading.current_thread()
            app_ref.state.base_station_start_time = time.time()
            app_ref.state.bs_phase = "running"
            app_ref.state.bs_error = None

            logger.info("[BS thread] RtkBaseStation started successfully")

        except Exception as e:
            logger.error(f"[BS thread] Initialization failed: {e}", exc_info=True)
            app_ref.state.bs_phase = "error"
            app_ref.state.bs_error = str(e)
            # If station was partially created, try to stop it
            station_local = getattr(app_ref.state, "base_station", None)
            if station_local:
                try:
                    station_local.stop()
                except Exception:
                    pass
                app_ref.state.base_station = None

    thread = threading.Thread(
        target=_run_initialization,
        args=(request.app,),
        daemon=True,
    )
    thread.start()

    logger.info("=== RTK Base Station start request accepted (background) ===")
    return {
        "status": "starting",
        "mode": bs_mode,
        "detail": "Base station initializing in background. Check /api/base_station/status for progress.",
    }


# ==========================================================================
# POST /api/base_station/stop — Stop RTK Base Station
# ==========================================================================

@router.post("/stop")
async def base_station_stop(request: Request):
    """Stop the RTK Base Station gracefully."""
    app = request.app
    station = getattr(app.state, "base_station", None)

    if station is None:
        return JSONResponse(
            {"status": "error", "detail": "Base station not running."},
            status_code=400,
        )

    logger.info("=== RTK Base Station stop requested ===")

    try:
        station.stop()
    except Exception as e:
        logger.warning(f"Base station stop error: {e}")

    # Clean up state
    app.state.base_station = None
    app.state.base_station_thread = None
    app.state.base_station_start_time = None

    logger.info("=== RTK Base Station stopped ===")
    return {"status": "ok", "detail": "Base station stopped."}


# ==========================================================================
# GET /api/base_station/status — Get current base station status
# ==========================================================================

@router.get("/status")
async def base_station_status(request: Request):
    """Get the current base station status, GPS fix, and RTCM statistics.

    Phases:
      - "idle":      Not started.
      - "starting":  Background initialization in progress (auto mode may take 60s).
      - "running":   Fully operational.
      - "error":     Initialization or runtime error.
    """
    app = request.app
    phase = getattr(app.state, "bs_phase", "idle")
    station = getattr(app.state, "base_station", None)

    # ── Not running or still starting ──────────────────────────────
    if station is None:
        bs_mode = _get_bs_mode()
        if phase == "starting":
            progress = getattr(app.state, "bs_progress", None)
            return {
                "running": False,
                "mode": bs_mode,
                "phase": "starting",
                "uptime_seconds": None,
                "gps": None,
                "serial": None,
                "tcp": None,
                "udp": None,
                "error": None,
                "progress": progress,
            }
        if phase == "error":
            return {
                "running": False,
                "mode": bs_mode,
                "phase": "error",
                "uptime_seconds": None,
                "gps": None,
                "serial": None,
                "tcp": None,
                "udp": None,
                "error": getattr(app.state, "bs_error", "Unknown error"),
            }
        return {
            "running": False,
            "mode": bs_mode,
            "phase": "idle",
            "uptime_seconds": None,
            "gps": None,
            "serial": None,
            "tcp": None,
            "udp": None,
            "error": None,
        }

    # ── Running ────────────────────────────────────────────────────
    # Read GPS status from the station
    gps_status = None
    try:
        gps_status = station._read_gps_status()
    except Exception:
        pass

    uptime = None
    start_time = getattr(app.state, "base_station_start_time", None)
    if start_time is not None:
        uptime = round(time.time() - start_time, 1)

    # Read component stats (safe access)
    serial_stats = None
    tcp_stats = None
    udp_stats = None

    try:
        serial_stats = station.serial_reader.stats if hasattr(station, 'serial_reader') else None
    except Exception:
        pass
    try:
        tcp_s = station.tcp_server.stats if hasattr(station, 'tcp_server') else None
        if tcp_s:
            tcp_stats = {
                "connections": tcp_s.get('connections', 0),
                "frames_sent": tcp_s.get('frames_sent', 0),
                "bytes_sent": tcp_s.get('bytes_sent', 0),
                "active_clients": len(tcp_s.get('clients', [])),
            }
    except Exception:
        pass
    try:
        udp_s = station.udp_broadcaster.stats if hasattr(station, 'udp_broadcaster') else None
        if udp_s:
            udp_stats = {
                "frames_sent": udp_s.get('frames_sent', 0),
                "bytes_sent": udp_s.get('bytes_sent', 0),
            }
    except Exception:
        pass

    bs_mode = _get_bs_mode()
    return {
        "running": True,
        "mode": bs_mode,
        "phase": "running",
        "uptime_seconds": uptime,
        "serial_port": station.config.serial_port if hasattr(station, 'config') else None,
        "gps": gps_status,
        "serial": serial_stats,
        "tcp": tcp_stats,
        "udp": udp_stats,
        "error": None,
    }
