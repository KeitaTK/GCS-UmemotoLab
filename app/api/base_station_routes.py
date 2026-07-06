"""app/api/base_station_routes.py — REST API for RTK Base Station (v2) control.

F9P設定 → RTCMシリアル読み取り → MAVLink GPS_RTCM_DATA注入 を一括で行う。
（TCP中継は不要になったため廃止）
"""

import logging
import threading
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("api.base_station")

router = APIRouter(prefix="/api/base_station", tags=["base_station"])


def _get_bs_mode() -> str:
    """Read base_station mode from hardware config."""
    try:
        from rtk_tools.config_loader import load_hardware_config
        hw = load_hardware_config()
        return hw.get('base_station', {}).get('mode', 'manual')
    except Exception:
        return 'manual'


@router.post("/start")
async def base_station_start(request: Request):
    """Start RTK base station and begin RTCM injection into ArduPilot.

    実行シーケンス:
      1. USBポート自動検出（auto モード時）
      2. 60秒単独測位で基準座標取得
      3. F9PをTMODE3 Fixed + RTCM3出力に設定
      4. COMポート閉じて再オープン
      5. RTCMフレーム読み取り開始 → MAVLink GPS_RTCM_DATA(#233) でPixhawkへ注入
      6. ログ保存
    """
    app = request.app
    phase = getattr(app.state, "bs_phase", "idle")
    serial_reader = getattr(app.state, "rtcm_serial_reader", None)
    if serial_reader is not None and serial_reader.running:
        return JSONResponse(
            {"status": "error", "detail": "RTCM injection already running. Stop it first."},
            status_code=409,
        )
    if phase == "starting":
        return JSONResponse(
            {"status": "error", "detail": "Already starting. Please wait."},
            status_code=409,
        )

    import api.server as api_srv

    if api_srv.connection is None:
        return JSONResponse(
            {"status": "error",
             "detail": "MAVLink not connected. Please POST /api/connect first, then start base station."},
            status_code=400,
        )

    logger.info("=== RTK Base Station start requested (integrated mode) ===")
    app.state.bs_phase = "starting"
    app.state.bs_error = None
    bs_mode = _get_bs_mode()

    def _run(app_ref):
        """Background thread: F9P setup -> RTCM serial read -> MAVLink inject."""
        best_samples = []  # populated in auto mode, empty for manual mode
        try:
            from rtk_tools.standalone_obs import (
                StandaloneObserver, auto_detect_port,
            )
            from rtk_tools.config_loader import load_hardware_config
            from rtk_tools.f9p_configurator import F9pConfigurator
            from rtk_tools.rtcm_serial_reader import RtcmSerialReader
            from rtk_tools.rtcm_injector import RtcmInjector
            from rtk_tools.rtcm_logger import RtcmLogger

            hw = load_hardware_config()
            bs = hw.get('base_station', {})
            obs_duration = int(bs.get('auto_obs_duration', 60))
            save_to_flash = bs.get('save_to_flash', True)
            f9p_baudrate = hw.get('f9p', {}).get('baudrate', 115200)

            # 1. ポート検出 + 基準座標取得
            serial_port = hw.get('f9p', {}).get('serial_port', 'COM8')
            fixed_lat = bs.get('fixed_lat')
            fixed_lon = bs.get('fixed_lon')
            fixed_alt = bs.get('fixed_alt')

            if bs_mode == 'auto':
                logger.info("[BS] Auto mode: detecting USB port...")
                serial_port = auto_detect_port()
                logger.info(f"[BS] Observing position for {obs_duration}s...")
                observer = StandaloneObserver(
                    port=serial_port,
                    baudrate=f9p_baudrate,
                    duration_sec=obs_duration,
                    progress_callback=lambda p: setattr(app_ref.state, 'bs_progress', p),
                )
                observer.run()
                if observer.samples:
                    from rtk_tools.standalone_obs import FIX_PRIORITY as FP
                    counts = {}
                    for s in observer.samples:
                        counts[s.fix_type] = counts.get(s.fix_type, 0) + 1
                    best_fix = max(counts.keys(), key=lambda ft: FP.get(ft, -1))
                    best_samples = [s for s in observer.samples if s.fix_type == best_fix]
                    if best_samples:
                        n = len(best_samples)
                        fixed_lat = sum(s.latitude for s in best_samples) / n
                        fixed_lon = sum(s.longitude for s in best_samples) / n
                        fixed_alt = sum(s.altitude for s in best_samples) / n
                        logger.info(
                            f"[BS] Fixed position: {fixed_lat:.7f}, "
                            f"{fixed_lon:.7f}, {fixed_alt:.2f}m"
                        )
                    else:
                        raise RuntimeError("Auto observation failed: no valid fix samples")
                else:
                    raise RuntimeError("Auto observation failed: no samples collected")

            if fixed_lat is None or fixed_lon is None or fixed_alt is None:
                raise RuntimeError(
                    "Fixed position not configured. Set fixed_lat/lon/alt or use auto mode."
                )

            # 2. F9P設定（TMODE3 Fixed + RTCM3出力）
            logger.info(f"[BS] Configuring F9P @ {f9p_baudrate} baud...")
            configurator = F9pConfigurator(
                serial_port=serial_port,
                baudrate=f9p_baudrate,
                logger=logging.getLogger("F9pConfigurator"),
            )
            results = configurator.configure(
                lat=fixed_lat, lon=fixed_lon, alt=fixed_alt,
                save_to_flash=save_to_flash,
            )
            logger.info(f"[BS] F9P config result: all_ok={results['all_ok']}")

            # 3. シリアルポート解放待機（Windowsは即座にopenすると失敗するため）
            logger.info(f"[BS] Waiting 1.5s for serial port to settle...")
            time.sleep(1.5)

            # 5. シリアル読み取り開始
            logger.info(f"[BS] Starting RTCM serial reader: {serial_port} @ {f9p_baudrate}")
            rtcm_serial_reader = RtcmSerialReader(
                serial_port=serial_port,
                baudrate=f9p_baudrate,
                enabled=True,
            )

            # 6. MAVLink送信用に MavlinkConnection を取得
            import api.server as api_srv
            mav_conn = api_srv.connection
            if mav_conn is None:
                raise RuntimeError("MAVLink not connected. POST /api/connect first.")

            rtcm_injector = RtcmInjector(enabled=True)
            rtcm_logger = RtcmLogger(enabled=True)
            logger.info("[BS] RTCM logger initialized")

            def _send_rtcm_frame(frame_data):
                try:
                    mav_conn.send_to_system(1, frame_data)
                    rtcm_logger.log_injected(frame_data)
                except Exception as e:
                    logger.error(f"RTCM send failed: {e}")

            rtcm_injector.set_send_callback(_send_rtcm_frame)

            def _poll_loop():
                while rtcm_serial_reader.running:
                    try:
                        frame = rtcm_serial_reader.queue.get(timeout=0.1)
                        rtcm_logger.log_raw(frame)
                        rtcm_injector.inject(frame)
                    except Exception:
                        pass

            rtcm_serial_reader.start()
            threading.Thread(target=_poll_loop, daemon=True).start()

            app_ref.state.rtcm_serial_reader = rtcm_serial_reader
            app_ref.state.rtcm_injector = rtcm_injector
            app_ref.state.rtcm_logger = rtcm_logger
            app_ref.state.bs_phase = "running"
            app_ref.state.bs_error = None
            app_ref.state.base_station_start_time = time.time()
            app_ref.state.rtcm_serial_port = serial_port
            # Save observed fixed position for Web UI display
            app_ref.state.bs_fixed_position = {
                "lat": fixed_lat,
                "lon": fixed_lon,
                "alt": fixed_alt,
                "fix_name": "3D_FIX (base)",
                "sats": len(best_samples) if best_samples else 0,
            }

            logger.info("[BS] RTCM injection started successfully")

        except Exception as e:
            logger.error(f"[BS] Initialization failed: {e}", exc_info=True)
            app_ref.state.bs_phase = "error"
            app_ref.state.bs_error = str(e)
            sr = getattr(app_ref.state, "rtcm_serial_reader", None)
            if sr:
                try:
                    sr.stop()
                except Exception:
                    pass
            lg = getattr(app_ref.state, "rtcm_logger", None)
            if lg:
                try:
                    lg.close()
                except Exception:
                    pass
            app_ref.state.rtcm_serial_reader = None
            app_ref.state.rtcm_injector = None
            app_ref.state.rtcm_logger = None

    thread = threading.Thread(target=_run, args=(request.app,), daemon=True)
    thread.start()

    logger.info("=== RTK Base Station start accepted (integrated) ===")
    return {
        "status": "starting",
        "mode": bs_mode,
        "detail": "RTCM injection starting in background (60s observation may be needed).",
    }


@router.post("/stop")
async def base_station_stop(request: Request):
    """Stop RTCM injection gracefully."""
    app = request.app
    reader = getattr(app.state, "rtcm_serial_reader", None)
    if reader is None:
        return JSONResponse(
            {"status": "error", "detail": "RTCM injection not running."},
            status_code=400,
        )

    logger.info("=== RTCM injection stop requested ===")
    errors = []
    if reader:
        try:
            reader.stop()
        except Exception as e:
            errors.append(f"reader: {e}")
    logger_obj = getattr(app.state, "rtcm_logger", None)
    if logger_obj:
        try:
            logger_obj.print_stats()
            logger_obj.close()
        except Exception as e:
            errors.append(f"logger: {e}")

    app.state.rtcm_serial_reader = None
    app.state.rtcm_injector = None
    app.state.rtcm_logger = None
    app.state.bs_phase = "idle"
    app.state.base_station_start_time = None

    logger.info("=== RTCM injection stopped ===")
    return {"status": "ok", "detail": "RTCM injection stopped.", "errors": errors if errors else None}


@router.get("/status")
async def base_station_status(request: Request):
    """Get the current RTCM injection status and statistics."""
    app = request.app
    phase = getattr(app.state, "bs_phase", "idle")
    reader = getattr(app.state, "rtcm_serial_reader", None)
    bs_mode = _get_bs_mode()

    base = {
        "running": (reader is not None and reader.running) if reader else False,
        "mode": bs_mode,
        "phase": phase,
        "error": None,
    }

    if phase == "starting":
        base["progress"] = getattr(app.state, "bs_progress", None)
        base["error"] = getattr(app.state, "bs_error", None)
        return base
    if phase == "error":
        base["error"] = getattr(app.state, "bs_error", "Unknown error")
        return base
    if phase == "idle":
        return base

    uptime = None
    start_time = getattr(app.state, "base_station_start_time", None)
    if start_time is not None:
        uptime = round(time.time() - start_time, 1)
    serial_port = getattr(app.state, "rtcm_serial_port", None)
    serial_stats = reader.stats if reader else None
    logger_obj = getattr(app.state, "rtcm_logger", None)
    rtcm_stats = logger_obj.get_stats() if logger_obj else None

    return {
        **base,
        "uptime_seconds": uptime,
        "serial_port": serial_port,
        "serial": serial_stats,
        "rtcm": rtcm_stats,
    }