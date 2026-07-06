/**
 * RTK Base Station control and status display for GCS Dashboard.
 * 
 * Provides:
 * - Start / Stop buttons for the RTK Base Station
 * - Real-time status display (GPS fix, RTCM frames, TCP clients)
 * - Periodic status refresh via WebSocket telemetryState (base_station field)
 */

// ==========================================================================
// DOM Refresher: reads base_station from the global telemetryState
// ==========================================================================

/**
 * Update the RTK Base Station panel in the status bar / dedicated section.
 * Called from dashboard.js updateDashboard() every WebSocket tick.
 */
function updateBaseStationUI() {
    var state = (typeof telemetryState !== 'undefined' && telemetryState.base_station) 
        ? telemetryState.base_station : null;

    var runningEl = document.getElementById('bs-running');
    var gpsFixEl = document.getElementById('bs-gps-fix');
    var gpsSatsEl = document.getElementById('bs-gps-sats');
    var gpsPosEl = document.getElementById('bs-gps-pos');
    var rtcmFramesEl = document.getElementById('bs-rtcm-frames');
    var tcpClientsEl = document.getElementById('bs-tcp-clients');
    var tcpFramesEl = document.getElementById('bs-tcp-frames');
    var udpFramesEl = document.getElementById('bs-udp-frames');
    var btnStart = document.getElementById('bs-btn-start');
    var btnStop = document.getElementById('bs-btn-stop');
    var phaseEl = document.getElementById('bs-phase');

    if (!runningEl) return; // panel not rendered

    var running = state && state.running === true;
    var phase = state ? (state.phase || 'idle') : 'idle';

    // Handle "starting" phase: show intermediate state
    if (phase === 'starting') {
        runningEl.textContent = '起動中...';
        runningEl.className = 'bs-status bs-starting';
        if (btnStart) btnStart.style.display = 'none';
        if (btnStop) btnStop.style.display = 'none';

        // Show progress info
        var prog = state ? state.progress : null;
        if (prog) {
            var remaining = prog.remaining_sec || 0;
            var fixName = prog.fix_name || '---';
            var bestFix = prog.best_fix_name || '---';
            var samples = prog.samples || 0;
            var sats = prog.satellites || 0;
            var hdop = prog.hdop || 0;
            if (phaseEl) phaseEl.textContent = '残り' + remaining + '秒 | Fix=' + fixName + ' | ' + samples + 'サンプル | 最高=' + bestFix;
            if (gpsFixEl) gpsFixEl.textContent = fixName;
            if (gpsSatsEl) gpsSatsEl.textContent = sats + ' sat';
            if (gpsPosEl) gpsPosEl.textContent = 'HDOP ' + hdop.toFixed(1);
        } else {
            if (phaseEl) phaseEl.textContent = '測位/設定中...';
            if (gpsFixEl) gpsFixEl.textContent = '--';
            if (gpsSatsEl) gpsSatsEl.textContent = '--';
            if (gpsPosEl) gpsPosEl.textContent = '--';
        }
        if (rtcmFramesEl) rtcmFramesEl.textContent = '--';
        if (tcpClientsEl) tcpClientsEl.textContent = '--';
        if (tcpFramesEl) tcpFramesEl.textContent = '--';
        if (udpFramesEl) udpFramesEl.textContent = '--';
        return;
    }

    // Handle "error" phase
    if (phase === 'error') {
        runningEl.textContent = 'エラー';
        runningEl.className = 'bs-status bs-error';
        if (phaseEl) phaseEl.textContent = state.error || '初期化失敗';
        if (btnStart) btnStart.style.display = '';
        if (btnStop) btnStop.style.display = 'none';
        return;
    }

    // Update visibility of start/stop buttons
    if (btnStart) btnStart.style.display = running ? 'none' : '';
    if (btnStop) btnStop.style.display = running ? '' : 'none';

    if (!running) {
        runningEl.textContent = '停止中';
        runningEl.className = 'bs-status bs-stopped';
        if (phaseEl) phaseEl.textContent = '';
        if (gpsFixEl) gpsFixEl.textContent = '--';
        if (gpsSatsEl) gpsSatsEl.textContent = '--';
        if (gpsPosEl) gpsPosEl.textContent = '--';
        if (rtcmFramesEl) rtcmFramesEl.textContent = '--';
        if (tcpClientsEl) tcpClientsEl.textContent = '--';
        if (tcpFramesEl) tcpFramesEl.textContent = '--';
        if (udpFramesEl) udpFramesEl.textContent = '--';
        return;
    }

    runningEl.textContent = '稼働中';
    runningEl.className = 'bs-status bs-running';

    // Phase (auto mode observation or running)
    if (phaseEl) {
        var mode = state.mode || 'manual';
        phaseEl.textContent = mode === 'auto' ? 'auto 測位/基地局' : 'manual 基地局';
    }

    // GPS fix info
    var gps = state.gps;
    if (gps && gpsFixEl) {
        var fixName = gps.fix_name || gps.fix || 'N/A';
        gpsFixEl.textContent = fixName;
    } else if (gpsFixEl) {
        gpsFixEl.textContent = '--';
    }

    if (gps && gpsSatsEl) {
        gpsSatsEl.textContent = gps.sats !== undefined ? gps.sats : '--';
    } else if (gpsSatsEl) {
        gpsSatsEl.textContent = '--';
    }

    if (gps && gpsPosEl) {
        var lat = gps.lat;
        var lon = gps.lon;
        var alt = gps.alt;
        if (lat !== undefined && lon !== undefined && alt !== undefined) {
            gpsPosEl.textContent = lat.toFixed(6) + ', ' + lon.toFixed(6) + ' @ ' + alt.toFixed(1) + 'm';
        } else {
            gpsPosEl.textContent = '--';
        }
    } else if (gpsPosEl) {
        gpsPosEl.textContent = '--';
    }

    // Serial / RTCM stats
    var serial = state.serial;
    if (serial && rtcmFramesEl) {
        rtcmFramesEl.textContent = (serial.frames_received || 0) + ' frames / ' + 
            formatBytes(serial.bytes_read || 0) + ' / err=' + (serial.read_errors || 0);
    } else if (rtcmFramesEl) {
        rtcmFramesEl.textContent = '--';
    }

    // TCP server stats
    var tcp = state.tcp;
    if (tcp && tcpClientsEl) {
        tcpClientsEl.textContent = (tcp.active_clients || 0);
    } else if (tcpClientsEl) {
        tcpClientsEl.textContent = '--';
    }
    if (tcp && tcpFramesEl) {
        tcpFramesEl.textContent = (tcp.frames_sent || 0) + ' frames / ' + 
            formatBytes(tcp.bytes_sent || 0);
    } else if (tcpFramesEl) {
        tcpFramesEl.textContent = '--';
    }

    // UDP stats
    var udp = state.udp;
    if (udp && udpFramesEl) {
        udpFramesEl.textContent = (udp.frames_sent || 0) + ' frames / ' +
            formatBytes(udp.bytes_sent || 0);
    } else if (udpFramesEl) {
        udpFramesEl.textContent = '--';
    }
}

/**
 * Format bytes to human-readable string.
 */
function formatBytes(bytes) {
    if (bytes === 0 || bytes === undefined || bytes === null) return '0B';
    var units = ['B', 'KB', 'MB', 'GB'];
    var i = Math.floor(Math.log(bytes) / Math.log(1024));
    if (i >= units.length) i = units.length - 1;
    return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + units[i];
}

// ==========================================================================
// API calls
// ==========================================================================

/**
 * Start the RTK Base Station.
 */
function startBaseStation() {
    var btnStart = document.getElementById('bs-btn-start');
    var statusEl = document.getElementById('bs-running');
    if (btnStart) btnStart.disabled = true;
    if (statusEl) { statusEl.textContent = '起動中...'; statusEl.className = 'bs-status bs-starting'; }

    fetch('/api/base_station/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status === 'starting') {
            if (statusEl) { statusEl.textContent = '起動中...'; statusEl.className = 'bs-status bs-starting'; }
            showToast('RTK基地局: バックグラウンドで起動中... (' + data.mode + ' mode)', 'info');
        } else {
            if (statusEl) { statusEl.textContent = 'エラー'; statusEl.className = 'bs-status bs-error'; }
            showToast('RTK基地局 起動エラー: ' + (data.detail || 'unknown'), 'error');
        }
    })
    .catch(function(err) {
        if (statusEl) { statusEl.textContent = 'エラー'; statusEl.className = 'bs-status bs-error'; }
        showToast('RTK基地局 起動エラー: ' + (err.message || err), 'error');
    })
    .finally(function() {
        if (btnStart) btnStart.disabled = false;
    });
}

/**
 * Stop the RTK Base Station.
 */
function stopBaseStation() {
    var btnStop = document.getElementById('bs-btn-stop');
    var statusEl = document.getElementById('bs-running');
    if (btnStop) btnStop.disabled = true;
    if (statusEl) { statusEl.textContent = '停止中...'; statusEl.className = 'bs-status bs-starting'; }

    fetch('/api/base_station/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status === 'ok') {
            if (statusEl) { statusEl.textContent = '停止済み'; statusEl.className = 'bs-status bs-stopped'; }
            showToast('RTK基地局: 停止完了', 'info');
        } else {
            if (statusEl) { statusEl.textContent = 'エラー'; statusEl.className = 'bs-status bs-error'; }
            showToast('RTK基地局 停止エラー: ' + (data.detail || 'unknown'), 'error');
        }
    })
    .catch(function(err) {
        if (statusEl) { statusEl.textContent = 'エラー'; statusEl.className = 'bs-status bs-error'; }
        showToast('RTK基地局 停止エラー: ' + (err.message || err), 'error');
    })
    .finally(function() {
        if (btnStop) btnStop.disabled = false;
    });
}

/**
 * Fetch base station status once (used on page load).
 */
function fetchBaseStationStatus() {
    fetch('/api/base_station/status')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        // The WebSocket will update the UI periodically,
        // but we force-update once to show initial state.
        updateBaseStationUI();
    })
    .catch(function(err) {
        console.warn('[BS] Failed to fetch initial status:', err);
    });
}

// ==========================================================================
// Initialization
// ==========================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Bind start button
    var btnStart = document.getElementById('bs-btn-start');
    if (btnStart) {
        btnStart.addEventListener('click', startBaseStation);
    }

    // Bind stop button
    var btnStop = document.getElementById('bs-btn-stop');
    if (btnStop) {
        btnStop.addEventListener('click', stopBaseStation);
    }

    // Fetch initial status
    fetchBaseStationStatus();
});