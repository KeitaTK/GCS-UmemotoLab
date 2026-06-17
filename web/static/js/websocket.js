/**
 * WebSocket connection manager for Multi-Drone Dashboard.
 * Connects to /ws/telemetry, maintains telemetryState + per-drone heartbeat tracking.
 */

var telemetryState = {};
let ws = null;
let wsRetryCount = 0;
const MAX_RETRIES = 10;
const HEARTBEAT_TIMEOUT_SEC = 5;

// Per-drone last-seen timestamps for offline detection
var droneLastSeen = {};

/**
 * Connect to the telemetry WebSocket endpoint.
 */
function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const port = location.port || '8000';
    const wsUrl = `${protocol}//${location.hostname}:${port}/ws/telemetry`;

    updateWsStatus('reconnecting');

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('[WS] Connected to', wsUrl);
        wsRetryCount = 0;
        updateWsStatus('connected');
    };

    ws.onmessage = (event) => {
        try {
            const payload = JSON.parse(event.data);
            if (payload.type === 'telemetry') {
                telemetryState = payload;

                // Update per-drone last-seen timestamps
                const now = Date.now() / 1000;
                if (payload.drones) {
                    for (const sysid of Object.keys(payload.drones)) {
                        const drone = payload.drones[sysid];
                        if (drone.heartbeat && drone.heartbeat.mode !== 'N/A') {
                            droneLastSeen[sysid] = now;
                        }
                    }
                }

                // Dispatch to dashboard update
                if (typeof updateDashboard === 'function') {
                    updateDashboard();
                }
            }
        } catch (e) {
            console.error('[WS] Failed to parse message:', e);
        }
    };

    ws.onclose = () => {
        console.warn('[WS] Connection closed');
        updateWsStatus('disconnected');
        scheduleReconnect();
    };

    ws.onerror = (err) => {
        console.error('[WS] Error:', err);
        updateWsStatus('disconnected');
    };
}

/**
 * Schedule a reconnection attempt with exponential backoff.
 */
function scheduleReconnect() {
    if (wsRetryCount >= MAX_RETRIES) {
        console.error('[WS] Max retries reached, giving up.');
        updateWsStatus('disconnected');
        return;
    }

    const delay = Math.min(5000 * Math.pow(2, wsRetryCount), 60000);
    wsRetryCount++;
    console.log(`[WS] Reconnecting in ${delay / 1000}s (attempt ${wsRetryCount}/${MAX_RETRIES})...`);
    updateWsStatus('reconnecting');

    setTimeout(() => {
        connectWebSocket();
    }, delay);
}

/**
 * Update the WS status indicator in the UI.
 */
function updateWsStatus(status) {
    const dot = document.getElementById('ws-dot');
    const text = document.getElementById('ws-text');
    if (!dot || !text) return;

    dot.className = 'status-dot';
    switch (status) {
        case 'connected':
            dot.classList.add('on');
            text.textContent = 'Connected';
            break;
        case 'disconnected':
            dot.classList.add('off');
            text.textContent = 'Disconnected';
            break;
        case 'reconnecting':
            dot.classList.add('off');
            text.textContent = `Reconnecting... (${wsRetryCount}/${MAX_RETRIES})`;
            break;
    }
}

/**
 * Check if a drone is considered online (has heartbeat within timeout).
 */
function isDroneOnline(sysid) {
    // Backend online flag takes priority when available
    const drones = telemetryState.drones || {};
    const drone = drones[String(sysid)];
    if (drone && drone.online !== undefined) {
        if (!drone.online) return false;
    }
    // Fallback: WebSocket-side heartbeat timeout detection
    const lastSeen = droneLastSeen[String(sysid)] || 0;
    return (Date.now() / 1000 - lastSeen) < HEARTBEAT_TIMEOUT_SEC;
}

/**
 * Get all currently online drone IDs.
 */
function getOnlineDroneIds() {
    const drones = telemetryState.drones || {};
    return Object.keys(drones).filter(id => {
        const drone = drones[id];
        return drone && drone.heartbeat && drone.heartbeat.mode !== 'N/A';
    }).map(Number);
}

// Expose getters globally
window.getTelemetryState = () => telemetryState;
window.isDroneOnline = isDroneOnline;
window.getOnlineDroneIds = getOnlineDroneIds;
window.droneLastSeen = droneLastSeen;

// Auto-connect when script loads
connectWebSocket();
