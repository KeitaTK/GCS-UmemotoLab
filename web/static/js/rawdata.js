/**
 * Raw data display for GCS Dashboard.
 * Shows telemetryState as formatted JSON in pre#raw-data-content.
 */

let rawDataScrollPos = 0;

function isRawDataTabActive() {
    const rawTab = document.getElementById('tab-raw');
    return rawTab ? rawTab.classList.contains('active') : false;
}

function updateRawData() {
    if (!isRawDataTabActive()) return;

    const pre = document.getElementById('raw-data-content');
    if (!pre) return;

    const sysid = getSelectedSystemId();
    if (sysid === null) { pre.textContent = 'No drone selected'; return; }

    const drones = telemetryState.drones || {};
    const drone = drones[String(sysid)];
    if (!drone) { pre.textContent = `No data for drone ${sysid}`; return; }

    rawDataScrollPos = pre.scrollTop;

    let output = `=== System ID: ${sysid} === Timestamp: ${telemetryState.timestamp || 'N/A'} ===\n\n`;

    if (telemetryState.connection) { output += '[CONNECTION]\n' + JSON.stringify(telemetryState.connection, null, 2) + '\n\n'; }

    for (const [key, value] of Object.entries(drone)) {
        output += `[${key.toUpperCase()}]\n`;
        output += (value && typeof value === 'object') ? JSON.stringify(value, null, 2) : String(value);
        output += '\n\n';
    }

    if (telemetryState.rtk) { output += '[RTK]\n' + JSON.stringify(telemetryState.rtk, null, 2) + '\n'; }

    pre.textContent = output;
    pre.scrollTop = rawDataScrollPos;
}
