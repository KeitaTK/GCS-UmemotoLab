/**
 * Multi-Drone Controls - Backend connect/disconnect, broadcast commands, per-drone STOP/Force Arm.
 */

/**
 * Connect to backend.
 */
function connectBackend() {
    const statusEl = document.getElementById('backend-status-text');
    if (statusEl) {
        statusEl.textContent = 'Connecting...';
        statusEl.className = 'status-value status-warn';
    }

    fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status === 'connected') {
            if (statusEl) {
                statusEl.textContent = 'Connected';
                statusEl.className = 'status-value status-ok';
            }
        } else {
            if (statusEl) {
                statusEl.textContent = 'Error: ' + (data.detail || 'unknown');
                statusEl.className = 'status-value status-error';
            }
        }
    })
    .catch(function(err) {
        if (statusEl) {
            statusEl.textContent = 'Error: ' + (err.message || err);
            statusEl.className = 'status-value status-error';
        }
    });
}

/**
 * Disconnect from backend.
 */
function disconnectBackend() {
    const statusEl = document.getElementById('backend-status-text');
    if (statusEl) {
        statusEl.textContent = 'Disconnecting...';
        statusEl.className = 'status-value status-warn';
    }

    fetch('/api/disconnect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status === 'disconnected') {
            if (statusEl) {
                statusEl.textContent = 'Not connected';
                statusEl.className = 'status-value status-warn';
            }
            // Clear drone data on disconnect
            droneLastSeen = {};
            telemetryState = {};
            if (typeof updateDashboard === 'function') updateDashboard();
        } else {
            if (statusEl) {
                statusEl.textContent = 'Error: ' + (data.detail || 'unknown');
                statusEl.className = 'status-value status-error';
            }
        }
    })
    .catch(function(err) {
        if (statusEl) {
            statusEl.textContent = 'Error: ' + (err.message || err);
            statusEl.className = 'status-value status-error';
        }
    });
}

/**
 * Get online drone IDs from current state.
 */
function _getOnlineIds() {
    if (typeof getOnlineDroneIds === 'function') {
        return getOnlineDroneIds();
    }
    const drones = telemetryState.drones || {};
    return Object.keys(drones)
        .filter(function(id) {
            const d = drones[id];
            return d && d.heartbeat && d.heartbeat.mode !== 'N/A';
        })
        .map(Number);
}

/**
 * Broadcast ARM to all online drones.
 */
function broadcastArm() {
    const ids = _getOnlineIds();
    if (ids.length === 0) { alert('No online drones to command.'); return; }
    if (!confirm('ARM ALL ' + ids.length + ' drone(s)?')) return;

    fetch('/api/arm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: ids, component_id: 1 })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { console.log('ARM ALL:', data); })
    .catch(function(err) { console.error('ARM ALL error:', err); });
}

/**
 * Broadcast DISARM to all online drones.
 */
function broadcastDisarm() {
    const ids = _getOnlineIds();
    if (ids.length === 0) { alert('No online drones to command.'); return; }
    if (!confirm('DISARM ALL ' + ids.length + ' drone(s)?')) return;

    fetch('/api/disarm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: ids, component_id: 1 })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { console.log('DISARM ALL:', data); })
    .catch(function(err) { console.error('DISARM ALL error:', err); });
}

/**
 * Broadcast TAKEOFF to all online drones.
 */
function broadcastTakeoff() {
    const ids = _getOnlineIds();
    if (ids.length === 0) { alert('No online drones to command.'); return; }

    const altInput = document.getElementById('takeoff-all-alt');
    const altitude = altInput ? parseFloat(altInput.value) || 10 : 10;

    if (!confirm('TAKEOFF ALL ' + ids.length + ' drone(s) to ' + altitude + 'm?')) return;

    fetch('/api/takeoff', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: ids, component_id: 1, altitude: altitude })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { console.log('TAKEOFF ALL:', data); })
    .catch(function(err) { console.error('TAKEOFF ALL error:', err); });
}

/**
 * Broadcast LAND to all online drones.
 */
function broadcastLand() {
    const ids = _getOnlineIds();
    if (ids.length === 0) { alert('No online drones to command.'); return; }
    if (!confirm('LAND ALL ' + ids.length + ' drone(s)?')) return;

    fetch('/api/land', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: ids, component_id: 1, descent_rate: 1.5 })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { console.log('LAND ALL:', data); })
    .catch(function(err) { console.error('LAND ALL error:', err); });
}

/**
 * Individual STOP (land) for a specific drone.
 */
function stopDrone(sysid) {
    if (!confirm('STOP (LAND) Drone ' + sysid + '?')) return;

    fetch('/api/land', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: [sysid], component_id: 1, descent_rate: 1.5 })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { console.log('STOP Drone ' + sysid + ':', data); })
    .catch(function(err) { console.error('STOP error:', err); });
}

/**
 * Individual Force Arm for a specific drone (dangerous, requires double confirm).
 */
function forceArmDrone(sysid) {
    if (!confirm('FORCE ARM Drone ' + sysid + '?\n\nThis will disable ARMING_CHECK and force arm.\nOnly for indoor testing!')) return;
    if (!confirm('CONFIRM: Force Arm Drone ' + sysid + '?\n\nPre-arm safety checks will be bypassed.')) return;

    fetch('/api/force_arm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_ids: [sysid], component_id: 1, confirmed: true })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        console.log('FORCE ARM Drone ' + sysid + ':', data);
        if (data.warning) {
            alert('Force Arm sent.\n\n' + data.warning);
        }
    })
    .catch(function(err) { console.error('FORCE ARM error:', err); });
}
