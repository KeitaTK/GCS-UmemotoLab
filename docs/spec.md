# GCS System Specification (Detailed)

## 1. Purpose
Build a custom Ground Control Station (GCS) for ArduPilot that directly uses MAVLink v2 over UDP, supports custom MAVLink messages, and enables multi-drone control on Windows.

## 2. Scope
### In scope
- MAVLink v2 UDP receive/transmit on Windows.
- RTK injection using `GPS_RTCM_DATA`.
- Telemetry reception including `NAMED_VALUE_FLOAT` and custom messages.
- Multi-drone identification by `SYSID_THISMAV`.
- Minimal operator UI using PySide6.
- Config-driven endpoint and system ID mapping.

### Out of scope
- ROS 2 integration.
- Onboard (Raspberry Pi) processing beyond `mavlink-router`.
- Mission planning UI equivalent to Mission Planner.

## 3. Assumptions
- Drone side: ArduPilot + `mavlink-router` forwarding to UDP.
- Custom MAVLink XML is available and used to generate `pymavlink`.
- Windows 10/11 with Python 3.10+.

## 4. Functional Requirements
### 4.1 Connection and Routing
- The GCS listens on UDP port `14550` by default.
- The GCS can send to multiple endpoints configured per system ID.
- The GCS must show connection status per drone using heartbeats.

### 4.2 Telemetry
- Receive and display:
  - `HEARTBEAT`
  - `NAMED_VALUE_FLOAT`
  - `SYS_STATUS`
  - `GLOBAL_POSITION_INT`
- Support custom MAVLink messages (generated `pymavlink`).
- Telemetry is stored in memory and available to UI for graphs.

### 4.3 Command and Control
- Send basic commands to a selected system ID:
  - Arm/Disarm (`MAV_CMD_COMPONENT_ARM_DISARM`)
  - Takeoff (`MAV_CMD_NAV_TAKEOFF`)
  - Land (`MAV_CMD_NAV_LAND`)
- Guided control via `SET_POSITION_TARGET_LOCAL_NED`.

### 4.4 RTK Injection
- Connect to local TCP port for RTCM stream (default `5000`).
- Encapsulate RTCM in `GPS_RTCM_DATA` and send to selected system ID(s).
- Support broadcast to all known system IDs.

### 4.5 Logging
- Log all received messages (filtered by type in config).
- Log errors, reconnect attempts, and command send results.

## 5. Non-Functional Requirements
- Latency from UDP receive to UI update: under 200 ms in normal load.
- Reconnect on UDP source loss without restarting.
- Stable operation with 3+ drones at 10 Hz telemetry each.

## 6. Interfaces
### 6.1 UDP MAVLink
- Listener: `udpin:0.0.0.0:14550` (default)
- Outbound: `udpout:<ip>:<port>` per drone or broadcast

### 6.2 RTCM TCP
- Local TCP server: `127.0.0.1:5000` (default)

## 7. Configuration
- File: `config/gcs.yml`
- Includes:
  - UDP listen port
  - Known drones: system ID to endpoint
  - RTCM host/port
  - Telemetry filters

## 8. Acceptance Criteria
- GCS shows heartbeat for at least one drone.
- `NAMED_VALUE_FLOAT` values are displayed and updated.
- Arm/Disarm commands reach the selected drone and report result.
- RTCM stream is forwarded and logged for at least one drone.

## 9. References
- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository
- https://docs.github.com/en/issues/tracking-your-work-with-issues/creating-an-issue
