/**
 * Flight Control & Selection handlers for GCS Dashboard.
 * Attaches click events to all command buttons.
 */

document.addEventListener('DOMContentLoaded', function() {

    // ===== Connect / Disconnect Backend =====
    document.getElementById('btn-connect').addEventListener('click', function() {
        var statusEl = document.getElementById('backend-status');
        if (statusEl) { statusEl.textContent = 'Connecting...'; statusEl.className = 'value status-neutral'; }
        fetch('/api/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status === 'connected') {
                if (statusEl) { statusEl.textContent = 'Connected'; statusEl.className = 'value status-ok'; }
            } else {
                if (statusEl) { statusEl.textContent = 'Error: ' + (data.detail || 'unknown'); statusEl.className = 'value status-error'; }
            }
        })
        .catch(function(err) {
            if (statusEl) { statusEl.textContent = 'Error: ' + (err.message || err); statusEl.className = 'value status-error'; }
        });
    });

    document.getElementById('btn-disconnect').addEventListener('click', function() {
        var statusEl = document.getElementById('backend-status');
        if (statusEl) { statusEl.textContent = 'Disconnecting...'; statusEl.className = 'value status-neutral'; }
        fetch('/api/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status === 'disconnected') {
                if (statusEl) { statusEl.textContent = 'Not connected'; statusEl.className = 'value status-neutral'; }
            } else {
                if (statusEl) { statusEl.textContent = 'Error: ' + (data.detail || 'unknown'); statusEl.className = 'value status-error'; }
            }
        })
        .catch(function(err) {
            if (statusEl) { statusEl.textContent = 'Error: ' + (err.message || err); statusEl.className = 'value status-error'; }
        });
    });

    // ===== Select All / Clear Selection =====
    document.getElementById('btn-select-all').addEventListener('click', function() {
        document.querySelectorAll('#drone-list li').forEach(function(li) {
            li.classList.add('selected');
        });
        if (typeof updateDashboard === 'function') updateDashboard();
    });

    document.getElementById('btn-clear-selection').addEventListener('click', function() {
        document.querySelectorAll('#drone-list li').forEach(function(li) {
            li.classList.remove('selected');
        });
        if (typeof updateDashboard === 'function') updateDashboard();
    });

    // ===== Arm =====
    document.getElementById('btn-arm').addEventListener('click', function() {
        var ids = getSelectedSystemIds();
        if (ids.length === 0) { alert('Please select a drone'); return; }
        fetch('/api/arm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ system_ids: ids, component_id: 1 })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) { updateCmdAck(data, 'Arm'); })
        .catch(function(err) { updateCmdAckError('Arm', err); });
    });

    // ===== Disarm =====
    document.getElementById('btn-disarm').addEventListener('click', function() {
        var ids = getSelectedSystemIds();
        if (ids.length === 0) { alert('Please select a drone'); return; }
        fetch('/api/disarm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ system_ids: ids, component_id: 1 })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) { updateCmdAck(data, 'Disarm'); })
        .catch(function(err) { updateCmdAckError('Disarm', err); });
    });

    // ===== Force Arm =====
    document.getElementById('btn-force-arm').addEventListener('click', function() {
        var ids = getSelectedSystemIds();
        if (ids.length === 0) { alert('Please select a drone'); return; }
        if (!confirm('⚠️ Force ArmはARMING_CHECK等を無効化します。屋内テスト専用。続行しますか？')) return;
        fetch('/api/force_arm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ system_ids: ids, component_id: 1, confirmed: true })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) { updateCmdAck(data, 'Force Arm'); })
        .catch(function(err) { updateCmdAckError('Force Arm', err); });
    });

    // ===== Takeoff =====
    document.getElementById('btn-takeoff').addEventListener('click', function() {
        var ids = getSelectedSystemIds();
        if (ids.length === 0) { alert('Please select a drone'); return; }
        var altInput = document.getElementById('takeoff-altitude');
        var altitude = altInput ? parseFloat(altInput.value) : 10.0;
        fetch('/api/takeoff', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ system_ids: ids, component_id: 1, altitude: altitude })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) { updateCmdAck(data, 'Takeoff'); })
        .catch(function(err) { updateCmdAckError('Takeoff', err); });
    });

    // ===== Land =====
    document.getElementById('btn-land').addEventListener('click', function() {
        var ids = getSelectedSystemIds();
        if (ids.length === 0) { alert('Please select a drone'); return; }
        var rateInput = document.getElementById('land-descent-rate');
        var descent_rate = rateInput ? parseFloat(rateInput.value) : 1.5;
        fetch('/api/land', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ system_ids: ids, component_id: 1, descent_rate: descent_rate })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) { updateCmdAck(data, 'Land'); })
        .catch(function(err) { updateCmdAckError('Land', err); });
    });

    // ===== Guided Position =====
    document.getElementById('btn-guided-position').addEventListener('click', function() {
        var ids = getSelectedSystemIds();
        if (ids.length === 0) { alert('Please select a drone'); return; }
        var north = parseFloat(document.getElementById('guided-north').value || 0);
        var east  = parseFloat(document.getElementById('guided-east').value || 0);
        var down  = parseFloat(document.getElementById('guided-down').value || 0);
        var yaw   = parseFloat(document.getElementById('guided-yaw').value || 0);
        fetch('/api/guided/position', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ system_ids: ids, component_id: 1, north: north, east: east, down: down, yaw: yaw })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) { updateCmdAck(data, 'Guided Position'); })
        .catch(function(err) { updateCmdAckError('Guided Position', err); });
    });

    // ===== Guided Velocity =====
    document.getElementById('btn-guided-velocity').addEventListener('click', function() {
        var ids = getSelectedSystemIds();
        if (ids.length === 0) { alert('Please select a drone'); return; }
        var vx  = parseFloat(document.getElementById('guided-vx').value || 0);
        var vy  = parseFloat(document.getElementById('guided-vy').value || 0);
        var vz  = parseFloat(document.getElementById('guided-vz').value || 0);
        var yaw = parseFloat(document.getElementById('guided-yaw-vel').value || 0);
        fetch('/api/guided/velocity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ system_ids: ids, component_id: 1, vx: vx, vy: vy, vz: vz, yaw: yaw })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) { updateCmdAck(data, 'Guided Velocity'); })
        .catch(function(err) { updateCmdAckError('Guided Velocity', err); });
    });

});

function updateCmdAck(data, label) {
    var el = document.getElementById('cmd-ack');
    if (!el) return;
    var status = data.status || 'unknown';
    if (status === 'ok' || status === 'sent' || status === 'partial') {
        el.textContent = label + ': ' + status;
        el.className = 'value status-ok';
    } else {
        el.textContent = label + ': ' + status;
        el.className = 'value status-error';
    }
}

function updateCmdAckError(label, err) {
    var el = document.getElementById('cmd-ack');
    if (!el) return;
    el.textContent = label + ': Error - ' + (err.message || err);
    el.className = 'value status-error';
}

// ===== Broadcast / Per-Drone Control Functions =====

/**
 * Get selected drone system IDs from #drone-list items with .selected class.
 */
function getSelectedSystemIds() {
    var ids = [];
    var items = document.querySelectorAll('#drone-list li.selected');
    items.forEach(function(li) {
        var sid = li.getAttribute('data-system-id');
        if (sid) ids.push(parseInt(sid, 10));
    });
    return ids;
}

/**
 * Get all currently online drone IDs.
 * Delegates to getOnlineDroneIds() from websocket.js if available,
 * otherwise falls back to telemetryState.drones.
 */
function _getOnlineIds() {
    if (typeof getOnlineDroneIds === 'function') {
        return getOnlineDroneIds();
    }
    var drones = (typeof telemetryState !== 'undefined' && telemetryState.drones) ? telemetryState.drones : {};
    var ids = [];
    for (var key in drones) {
        if (drones.hasOwnProperty(key)) {
            ids.push(parseInt(key, 10));
        }
    }
    return ids;
}

/**
 * Broadcast Arm to all online drones.
 */
function broadcastArm() {
    var ids = _getOnlineIds();
    if (ids.length === 0) { alert('No online drones'); return; }
    if (!confirm('ARM ALL ' + ids.length + ' drone(s)?')) return;
    fetch('/api/arm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: ids })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { updateCmdAck(data, 'Broadcast Arm'); })
    .catch(function(err) { updateCmdAckError('Broadcast Arm', err); });
}

/**
 * Broadcast Disarm to all online drones.
 */
function broadcastDisarm() {
    var ids = _getOnlineIds();
    if (ids.length === 0) { alert('No online drones'); return; }
    if (!confirm('DISARM ALL ' + ids.length + ' drone(s)?')) return;
    fetch('/api/disarm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: ids })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { updateCmdAck(data, 'Broadcast Disarm'); })
    .catch(function(err) { updateCmdAckError('Broadcast Disarm', err); });
}

/**
 * Broadcast Takeoff to all online drones.
 */
function broadcastTakeoff() {
    var ids = _getOnlineIds();
    if (ids.length === 0) { alert('No online drones'); return; }
    var altInput = document.getElementById('takeoff-all-alt');
    var altitude = altInput ? parseFloat(altInput.value) : 10.0;
    if (!confirm('TAKEOFF ALL ' + ids.length + ' drone(s) to ' + altitude + 'm?')) return;
    fetch('/api/takeoff', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: ids, altitude: altitude })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { updateCmdAck(data, 'Broadcast Takeoff'); })
    .catch(function(err) { updateCmdAckError('Broadcast Takeoff', err); });
}

/**
 * Broadcast Land to all online drones.
 */
function broadcastLand() {
    var ids = _getOnlineIds();
    if (ids.length === 0) { alert('No online drones'); return; }
    if (!confirm('LAND ALL ' + ids.length + ' drone(s)?')) return;
    fetch('/api/land', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: ids, descent_rate: 1.5 })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { updateCmdAck(data, 'Broadcast Land'); })
    .catch(function(err) { updateCmdAckError('Broadcast Land', err); });
}

/**
 * Stop (Land immediately) a single drone by system ID.
 */
function stopDrone(sysid) {
    if (!confirm('STOP Drone ' + sysid + ' (Land immediately)?')) return;
    fetch('/api/land', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: [sysid] })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { updateCmdAck(data, 'Stop Drone-' + sysid); })
    .catch(function(err) { updateCmdAckError('Stop Drone-' + sysid, err); });
}

/**
 * Force Arm a single drone (double confirm for safety).
 */
function forceArmDrone(sysid) {
    if (!confirm('\u26A0\uFE0F Force Arm Drone ' + sysid + '?\n(ARMING_CHECK bypass - \u5C4B\u5185\u30C6\u30B9\u30C8\u5C02\u7528)')) return;
    if (!confirm('\u672C\u5F53\u306BForce Arm\u3057\u307E\u3059\u304B\uFF1F\nDrone ' + sysid)) return;
    fetch('/api/force_arm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: [sysid], confirmed: true })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { updateCmdAck(data, 'Force Arm Drone-' + sysid); })
    .catch(function(err) { updateCmdAckError('Force Arm Drone-' + sysid, err); });
}
