/**
 * Real-time graph plotting for GCS Dashboard.
 * Uses Plotly.js for battery voltage and GPS altitude graphs.
 */

const MAX_POINTS = 60;
let batteryTimestamps = [];
let batteryVoltages = [];
let altitudeTimestamps = [];
let altitudeValues = [];
let batteryChartReady = false;
let altitudeChartReady = false;

function initGraphs() {
    const traceBatt = {
        x: [], y: [], type: 'scatter', mode: 'lines+markers', name: 'Battery Voltage',
        line: { color: '#e67e22', width: 2 }, marker: { color: '#e67e22', size: 4 },
    };
    const layoutBatt = {
        title: { text: 'Battery Voltage', font: { color: '#e0e0e0' } },
        xaxis: { title: { text: 'Time (s ago)', font: { color: '#888' } }, color: '#888', gridcolor: '#0f3460', zerolinecolor: '#0f3460' },
        yaxis: { title: { text: 'Voltage (V)', font: { color: '#888' } }, color: '#888', gridcolor: '#0f3460', zerolinecolor: '#0f3460' },
        plot_bgcolor: '#16213e', paper_bgcolor: '#16213e', font: { color: '#e0e0e0' }, margin: { l: 50, r: 20, t: 40, b: 40 }, showlegend: true, legend: { font: { color: '#e0e0e0' } },
    };
    const config = { responsive: true, displayModeBar: false };

    if (document.getElementById('graph-container')) { Plotly.newPlot('graph-container', [traceBatt], layoutBatt, config); batteryChartReady = true; }

    const traceAlt = {
        x: [], y: [], type: 'scatter', mode: 'lines+markers', name: 'GPS Altitude',
        line: { color: '#2ecc71', width: 2 }, marker: { color: '#2ecc71', size: 4 },
    };
    const layoutAlt = {
        title: { text: 'GPS Altitude', font: { color: '#e0e0e0' } },
        xaxis: { title: { text: 'Time (s ago)', font: { color: '#888' } }, color: '#888', gridcolor: '#0f3460', zerolinecolor: '#0f3460' },
        yaxis: { title: { text: 'Altitude (m)', font: { color: '#888' } }, color: '#888', gridcolor: '#0f3460', zerolinecolor: '#0f3460' },
        plot_bgcolor: '#16213e', paper_bgcolor: '#16213e', font: { color: '#e0e0e0' }, margin: { l: 50, r: 20, t: 40, b: 40 }, showlegend: true, legend: { font: { color: '#e0e0e0' } },
    };
    if (document.getElementById('graph-altitude-container')) { Plotly.newPlot('graph-altitude-container', [traceAlt], layoutAlt, config); altitudeChartReady = true; }
}

function isGraphTabActive() {
    const graphTab = document.getElementById('tab-graph');
    return graphTab ? graphTab.classList.contains('active') : false;
}

function updateGraphs() {
    if (!isGraphTabActive()) return;

    const now = Date.now() / 1000;
    const sysid = getSelectedSystemId();
    if (sysid === null) return;

    const drones = telemetryState.drones || {};
    const drone = drones[String(sysid)];
    if (!drone) return;

    const batt = drone.battery;
    if (batt && batt.voltage !== null) {
        batteryTimestamps.push(now);
        batteryVoltages.push(batt.voltage);
        if (batteryTimestamps.length > MAX_POINTS) { batteryTimestamps.shift(); batteryVoltages.shift(); }
        if (batteryChartReady) {
            const xDisplay = batteryTimestamps.map(t => Number((now - t).toFixed(1)));
            Plotly.extendTraces('graph-container', { x: [[xDisplay[xDisplay.length - 1]]], y: [[batt.voltage]] }, [0], MAX_POINTS);
            Plotly.animate('graph-container', { data: [{ x: xDisplay, y: batteryVoltages }], traces: [0] }, { transition: { duration: 0 }, frame: { duration: 0, redraw: false } });
        }
    }

    const gps = drone.gps;
    if (gps && gps.alt !== null) {
        altitudeTimestamps.push(now);
        altitudeValues.push(gps.alt);
        if (altitudeTimestamps.length > MAX_POINTS) { altitudeTimestamps.shift(); altitudeValues.shift(); }
        if (altitudeChartReady) {
            const xDisplay = altitudeTimestamps.map(t => Number((now - t).toFixed(1)));
            Plotly.extendTraces('graph-altitude-container', { x: [[xDisplay[xDisplay.length - 1]]], y: [[gps.alt]] }, [0], MAX_POINTS);
            Plotly.animate('graph-altitude-container', { data: [{ x: xDisplay, y: altitudeValues }], traces: [0] }, { transition: { duration: 0 }, frame: { duration: 0, redraw: false } });
        }
    }
}

window.addEventListener('load', () => {
    if (typeof Plotly !== 'undefined') { initGraphs(); }
    else {
        console.warn('[Graph] Plotly not loaded yet, retrying...');
        const checkPlotly = setInterval(() => { if (typeof Plotly !== 'undefined') { clearInterval(checkPlotly); initGraphs(); } }, 200);
    }
});
