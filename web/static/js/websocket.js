/**
 * WebSocket connection manager for GCS Dashboard.
 * Connects to /ws/telemetry and maintains telemetryState.
 */

let telemetryState = {};
let ws = null;
let wsRetryCount = 0;
const MAX_RETRIES = 10;

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
                if (typeof updateDashboard === 'function') updateDashboard();
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

    setTimeout(() => { connectWebSocket(); }, delay);
}

function updateWsStatus(status) {
    const dot = document.getElementById('ws-status-dot');
    const text = document.getElementById('ws-status-text');
    if (!dot || !text) return;

    dot.className = '';
    switch (status) {
        case 'connected':
            dot.classList.add('connected');
            text.textContent = 'Connected';
            text.className = 'status-ok';
            break;
        case 'disconnected':
            dot.classList.add('disconnected');
            text.textContent = 'Disconnected';
            text.className = 'status-error';
            break;
        case 'reconnecting':
            dot.classList.add('reconnecting');
            text.textContent = `Reconnecting... (${wsRetryCount}/${MAX_RETRIES})`;
            text.className = 'status-warn';
            break;
    }
}

window.getTelemetryState = () => telemetryState;

connectWebSocket();
