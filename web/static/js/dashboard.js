/**
 * Dashboard update functions for GCS Dashboard.
 * Reads from telemetryState and updates all UI sections.
 */

/**
 * Get the currently selected drone's system_id.
 * Returns the first selected ID, or null if none selected.
 */
function getSelectedSystemId() {
    const items = document.querySelectorAll('#drone-list li.selected');
    if (items.length === 0) return null;
    return parseInt(items[0].textContent, 10);
}

/**
 * Get all selected system_ids.
 */
function getSelectedSystemIds() {
    const items = document.querySelectorAll('#drone-list li.selected');
    return Array.from(items).map(li => parseInt(li.textContent, 10));
}

/**
 * Main update function - called from websocket onmessage.
 */
function updateDashboard() {
    const sysid = getSelectedSystemId();
    updateDroneList();

    if (sysid === null) {
        clearDashboard();
        return;
    }

    const drones = telemetryState.drones || {};
    const drone = drones[String(sysid)];
    if (!drone) {
        clearDashboard();
        return;
    }

    updateConnectionStatus(telemetryState.connection);
    updateSystemStatus(drone.heartbeat, drone.system_state);
    updateBatteryStatus(drone.battery);
    updateGpsStatus(drone.gps);
    updateRtkStatus(telemetryState.rtk);
    updateCommandStatus(drone.command_state);
}

/**
 * Clear all dashboard values to N/A.
 */
function clearDashboard() {
    const ids = [
        'conn-status', 'conn-type', 'conn-packets', 'conn-error',
        'sys-armed', 'sys-mode',
        'batt-voltage', 'batt-current', 'batt-remaining',
        'gps-fix', 'gps-sats', 'gps-coords', 'gps-alt', 'gps-hdop',
        'rtk-status',
        'cmd-last', 'cmd-ack', 'cmd-pending', 'cmd-retries'
    ];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = 'N/A';
    });
}

/**
 * Dynamically update the drone list from telemetryState keys.
 */
function updateDroneList() {
    const list = document.getElementById('drone-list');
    if (!list) return;

    const drones = telemetryState.drones || {};
    const currentSelected = new Set(getSelectedSystemIds().map(String));

    list.innerHTML = '';
    Object.keys(drones).sort((a, b) => parseInt(a) - parseInt(b)).forEach(sysid => {
        const li = document.createElement('li');
        li.textContent = sysid;
        li.dataset.sysid = sysid;
        if (currentSelected.has(sysid)) {
            li.classList.add('selected');
        }

        li.addEventListener('click', (e) => {
            if (e.ctrlKey || e.metaKey) {
                li.classList.toggle('selected');
            } else {
/**
 * Update Connection Status section.
 */
function updateConnectionStatus(conn) {
    if (!conn) {
        setText('conn-status', 'N/A', 'status-neutral');
        setText('conn-type', 'N/A', 'status-neutral');
        setText('conn-packets', 'N/A', 'status-neutral');
        setText('conn-error', 'N/A', 'status-neutral');
        return;
    }
    const connected = conn.is_connected;
    setText('conn-status', connected ? 'Connected' : 'Disconnected',
        connected ? 'status-ok' : 'status-error');
    setText('conn-type', conn.type || 'unknown', 'status-neutral');
    const pkts = `RX: ${conn.packets_received || 0} Loss: ${conn.packet_loss || 0}`;
    setText('conn-packets', pkts, 'status-neutral');
    const err = conn.last_error || 'None';
    setText('conn-error', err, err === 'None' ? 'status-ok' : 'status-warn');
}

/**
 * Update System Status section.
 */
function updateSystemStatus(hb, sysState) {
    const heartbeat = hb || sysState;
    if (!heartbeat) {
        setHtml('sys-armed', '🔴 DISARMED', 'status-neutral');
        setText('sys-mode', 'N/A', 'status-neutral');
        return;
    }
    const armed = heartbeat.armed;
    setHtml('sys-armed',
        armed ? '<span class="status-ok">🟢 ARMED</span>' : '<span class="status-error">🔴 DISARMED</span>',
        '');
    setText('sys-mode', heartbeat.mode || 'N/A', armed ? 'status-ok' : 'status-neutral');
}

/**
 * Update Battery Status section.
 */
function updateBatteryStatus(batt) {
    if (!batt || batt.voltage === null) {
        setText('batt-voltage', 'N/A', 'status-neutral');
        setText('batt-current', 'N/A', 'status-neutral');
        setText('batt-remaining', 'N/A', 'status-neutral');
        return;
    }
    setText('batt-voltage', `${batt.voltage} V`, 'status-ok');
    setText('batt-current',
        batt.current !== null ? `${batt.current} A` : 'N/A', 'status-neutral');
    setText('batt-remaining',
        batt.remaining !== null ? `${batt.remaining}%` : 'N/A',
        batt.remaining !== null && batt.remaining < 20 ? 'status-error' : 'status-ok');
}

/**
 * Update GPS Status section.
 * Color logic: RTK (fix_type >= 5) = green, 3D/DGPS (3-4) = orange, else red.
 */
function updateGpsStatus(gps) {
    if (!gps || gps.fix_type < 0) {
        setHtml('gps-fix', 'N/A', 'status-neutral');
        setText('gps-sats', 'N/A', 'status-neutral');
        setText('gps-coords', 'N/A', 'status-neutral');
        setText('gps-alt', 'N/A', 'status-neutral');
        setText('gps-hdop', 'N/A', 'status-neutral');
        return;
    }
    const fixType = gps.fix_type;
    const fixName = gps.fix_name || `UNKNOWN(${fixType})`;
    let fixClass = 'status-error';
    if (fixType >= 5) fixClass = 'status-ok';
    else if (fixType >= 3) fixClass = 'status-warn';

    setHtml('gps-fix', `<span class="${fixClass}">${fixName}</span>`, '');
    setText('gps-sats', `${gps.satellites || 0} sats`, 'status-neutral');
    const lat = gps.lat !== null && gps.lat !== undefined ? gps.lat.toFixed(6) : 'N/A';
    const lon = gps.lon !== null && gps.lon !== undefined ? gps.lon.toFixed(6) : 'N/A';
    setText('gps-coords', `${lat}, ${lon}`, 'status-neutral');
    setText('gps-alt', gps.alt !== null ? `${gps.alt} m` : 'N/A', 'status-neutral');
    setText('gps-hdop', gps.hdop !== null ? `${gps.hdop} m` : 'N/A',
        gps.hdop !== null && gps.hdop < 1.0 ? 'status-ok' : 'status-warn');
}

/**
 * Update RTK Status section.
 */
function updateRtkStatus(rtk) {
    if (!rtk) {
        setText('rtk-status', 'N/A', 'status-neutral');
        return;
    }
    const msg = `enabled=${rtk.enabled || false} messages=${rtk.messages_received || 0} ` +
                `connections=${rtk.connections || 0} reconnects=${rtk.reconnects || 0}`;
    setText('rtk-status', msg, rtk.enabled ? 'status-ok' : 'status-neutral');
}

/**
 * Update Command Status section.
 */
function updateCommandStatus(cmdState) {
    if (!cmdState) {
        setText('cmd-last', 'N/A', 'status-neutral');
        setText('cmd-ack', 'N/A', 'status-neutral');
        setText('cmd-pending', 'N/A', 'status-neutral');
        setText('cmd-retries', 'N/A', 'status-neutral');
        return;
    }
    const lastAck = cmdState.last_ack;
    setText('cmd-last', lastAck ? lastAck.command || '-' : '-', 'status-neutral');

    if (lastAck) {
        const ackClass = lastAck.status === 'acked' ? 'status-ok' :
                         (lastAck.status === 'failed' || lastAck.status === 'timeout') ? 'status-error' : 'status-warn';
        setText('cmd-ack', lastAck.status, ackClass);
    } else {
        setText('cmd-ack', 'Waiting...', 'status-warn');
    }

    setText('cmd-pending', String(cmdState.pending_count || 0), 'status-neutral');
    setText('cmd-retries', `0/3`, 'status-neutral');
}

/**
 * Helper: set an element's text content and class.
 */
function setText(id, text, className) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    if (className) {
        el.className = `value ${className}`;
    }
}

/**
 * Helper: set an element's inner HTML and class.
 */
function setHtml(id, html, className) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = html;
    if (className) {
        el.className = `value ${className}`;
    }
}

                document.querySelectorAll('#drone-list li').forEach(item => {
                    item.classList.remove('selected');
                });
                li.classList.add('selected');
            }
            updateDashboard();
        });

        list.appendChild(li);
    });
}