/**
 * Dashboard update functions for GCS Cockpit Dashboard.
 * Reads from telemetryState and updates all UI sections.
 */

function setText(id, text, className) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    if (className) el.className = 'value ' + className;
}

function setHtml(id, html, className) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = html;
    if (className) el.className = 'value ' + className;
}

function getSelectedSystemId() {
    const items = document.querySelectorAll('#drone-list li.selected');
    if (items.length === 0) return null;
    return parseInt(items[0].textContent, 10);
}

function getSelectedSystemIds() {
    const items = document.querySelectorAll('#drone-list li.selected');
    return Array.from(items).map(li => parseInt(li.textContent, 10));
}

function updateDashboard() {
    const sysid = getSelectedSystemId();
    updateDroneList();
    updateSidebarConnection(telemetryState.connection);

    if (sysid === null) { clearDashboard(); return; }

    const drones = telemetryState.drones || {};
    const drone = drones[String(sysid)];
    if (!drone) { clearDashboard(); return; }

    updateConnectionStatus(telemetryState.connection);
    updateSystemStatus(drone.heartbeat, drone.system_state);
    updateBatteryStatus(drone.battery);
    updateGpsStatus(drone.gps);
    updateRtkStatus(telemetryState.rtk);
    updateCommandStatus(drone.command_state);
}

function updateSidebarConnection(conn) {
    const dot = document.getElementById('sidebar-conn-dot');
    const text = document.getElementById('sidebar-conn-text');
    if (!dot || !text) return;
    if (!conn || !conn.is_connected) {
        dot.className = 'disconnected';
        text.textContent = 'No Connection';
    } else {
        dot.className = 'connected';
        text.textContent = conn.type ? conn.type.toUpperCase() + ' Connected' : 'Connected';
    }
}

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

    const fill = document.getElementById('battery-fill');
    if (fill) { fill.style.width = '0%'; fill.className = 'battery-gauge-fill'; }
    const voltDisp = document.getElementById('batt-voltage-display');
    if (voltDisp) voltDisp.textContent = '--.- V';
    const pctDisp = document.getElementById('batt-pct-display');
    if (pctDisp) pctDisp.textContent = '--%';

    const lamp = document.getElementById('conn-lamp');
    if (lamp) lamp.classList.remove('on');
}

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
        if (currentSelected.has(sysid)) li.classList.add('selected');

        li.addEventListener('click', function(e) {
            if (e.ctrlKey || e.metaKey) {
                li.classList.toggle('selected');
            } else {
                document.querySelectorAll('#drone-list li').forEach(function(item) {
                    item.classList.remove('selected');
                });
                li.classList.add('selected');
            }
            updateDashboard();
        });

        list.appendChild(li);
    });
}

function updateConnectionStatus(conn) {
    const lamp = document.getElementById('conn-lamp');

    if (!conn) {
        setText('conn-status', 'N/A', 'status-neutral');
        setText('conn-type', 'N/A', 'status-neutral');
        setText('conn-packets', 'N/A', 'status-neutral');
        setText('conn-error', 'N/A', 'status-neutral');
        if (lamp) lamp.classList.remove('on');
        return;
    }

    const connected = conn.is_connected;
    if (lamp) { if (connected) lamp.classList.add('on'); else lamp.classList.remove('on'); }

    setText('conn-status', connected ? 'Connected' : 'Disconnected', connected ? 'status-ok' : 'status-error');
    setText('conn-type', conn.type || 'unknown', 'status-neutral');
    setText('conn-packets', 'RX: ' + (conn.packets_received || 0) + ' Loss: ' + (conn.packet_loss || 0), 'status-neutral');
    setText('conn-error', conn.last_error || 'None', conn.last_error ? 'status-warn' : 'status-ok');
}

function updateSystemStatus(hb, sysState) {
    const heartbeat = hb || sysState;
    if (!heartbeat) {
        setHtml('sys-armed', '🔴 DISARMED', 'status-neutral');
        setText('sys-mode', 'N/A', 'status-neutral');
        return;
    }
    const armed = heartbeat.armed;
    setHtml('sys-armed', armed ? '<span class="status-ok">🟢 ARMED</span>' : '<span class="status-error">🔴 DISARMED</span>', '');
    setText('sys-mode', heartbeat.mode || 'N/A', armed ? 'status-ok' : 'status-neutral');
}

function updateBatteryStatus(batt) {
    const fillEl = document.getElementById('battery-fill');
    const voltDisp = document.getElementById('batt-voltage-display');
    const pctDisp = document.getElementById('batt-pct-display');

    if (!batt || batt.voltage === null) {
        setText('batt-voltage', 'N/A', 'status-neutral');
        setText('batt-current', 'N/A', 'status-neutral');
        setText('batt-remaining', 'N/A', 'status-neutral');
        if (fillEl) { fillEl.style.width = '0%'; fillEl.className = 'battery-gauge-fill'; }
        if (voltDisp) voltDisp.textContent = '--.- V';
        if (pctDisp) pctDisp.textContent = '--%';
        return;
    }

    setText('batt-voltage', batt.voltage.toFixed(2) + ' V', 'status-ok');
    setText('batt-current', batt.current !== null ? batt.current.toFixed(1) + ' A' : 'N/A', 'status-neutral');

    const remaining = batt.remaining !== null ? batt.remaining : 0;
    setText('batt-remaining', remaining + '%', remaining < 20 ? 'status-error' : 'status-ok');

    if (fillEl) {
        fillEl.style.width = Math.max(0, Math.min(100, remaining)) + '%';
        if (remaining > 50) fillEl.className = 'battery-gauge-fill green';
        else if (remaining > 25) fillEl.className = 'battery-gauge-fill yellow';
        else fillEl.className = 'battery-gauge-fill red';
    }

    if (voltDisp) voltDisp.textContent = batt.voltage.toFixed(1) + ' V';
    if (pctDisp) pctDisp.textContent = remaining + '%';
}

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
    const fixName = gps.fix_name || 'UNKNOWN(' + fixType + ')';
    let fixClass = 'status-error';
    if (fixType >= 5) fixClass = 'status-ok';
    else if (fixType >= 3) fixClass = 'status-warn';

    setHtml('gps-fix', '<span class="' + fixClass + '">' + fixName + '</span>', '');
    setText('gps-sats', (gps.satellites || 0) + ' sats', 'status-neutral');
    const lat = gps.lat !== null && gps.lat !== undefined ? gps.lat.toFixed(6) : 'N/A';
    const lon = gps.lon !== null && gps.lon !== undefined ? gps.lon.toFixed(6) : 'N/A';
    setText('gps-coords', lat + ', ' + lon, 'status-neutral');
    setText('gps-alt', gps.alt !== null ? gps.alt.toFixed(1) + ' m' : 'N/A', 'status-neutral');
    setText('gps-hdop', gps.hdop !== null ? gps.hdop.toFixed(2) + ' m' : 'N/A', gps.hdop !== null && gps.hdop < 1.0 ? 'status-ok' : 'status-warn');
}

function updateRtkStatus(rtk) {
    if (!rtk) { setText('rtk-status', 'N/A', 'status-neutral'); return; }
    const msg = 'enabled=' + (rtk.enabled || false) + ' messages=' + (rtk.messages_received || 0) + ' connections=' + (rtk.connections || 0) + ' reconnects=' + (rtk.reconnects || 0);
    setText('rtk-status', msg, rtk.enabled ? 'status-ok' : 'status-neutral');
}

function updateCommandStatus(cmdState) {
    if (!cmdState) {
        setText('cmd-last', 'N/A', 'status-neutral');
        setText('cmd-ack', 'N/A', 'status-neutral');
        setText('cmd-pending', 'N/A', 'status-neutral');
        setText('cmd-retries', 'N/A', 'status-neutral');
        return;
    }
    const lastAck = cmdState.last_ack;
    setText('cmd-last', lastAck ? (lastAck.command || '-') : '-', 'status-neutral');
    if (lastAck) {
        const ackClass = lastAck.status === 'acked' ? 'status-ok' : (lastAck.status === 'failed' || lastAck.status === 'timeout') ? 'status-error' : 'status-warn';
        setText('cmd-ack', lastAck.status, ackClass);
    } else {
        setText('cmd-ack', 'Waiting...', 'status-warn');
    }
    setText('cmd-pending', String(cmdState.pending_count || 0), 'status-neutral');
    setText('cmd-retries', '0/3', 'status-neutral');
}
