---
name: GCS MVP Implementation
about: Implement custom GCS with MAVLink v2 UDP, RTK injection, and multi-drone control
labels: [gcs, mvp]
---

## Summary
Build a Python GCS on Windows that directly speaks MAVLink v2 over UDP, supports custom messages, and provides RTK injection and basic command/control.

## Scope
- MAVLink v2 UDP receive/transmit
- Custom MAVLink message support
- RTK injection via `GPS_RTCM_DATA`
- Multi-drone management by system ID
- Minimal PySide6 UI

## Detailed Requirements
### Connection
- Listen on UDP `14550`
- Configurable outbound endpoints per system ID
- Display heartbeat status per drone

### Telemetry
- Receive `HEARTBEAT`, `NAMED_VALUE_FLOAT`, `SYS_STATUS`, `GLOBAL_POSITION_INT`
- Support custom messages from generated `pymavlink`
- Store latest values in memory

### Command and Control
- Arm/Disarm, Takeoff, Land
- Guided control via `SET_POSITION_TARGET_LOCAL_NED`

### RTK Injection
- Read RTCM from local TCP `127.0.0.1:5000`
- Send `GPS_RTCM_DATA` to selected system IDs

## Architecture (Planned)
- `MavlinkConnection`, `MessageRouter`, `TelemetryStore`
- `RtcmReader`, `RtcmInjector`
- `CommandDispatcher`, `GuidedControl`
- `MainWindow`, `DroneState`

## Concurrency
- Threaded UDP receive and TCP RTCM read
- UI in main thread using Qt signals
- No multiprocessing in MVP

## Acceptance Criteria
- Heartbeat detected for at least one drone
- `NAMED_VALUE_FLOAT` shown in UI
- Command send succeeds to selected system ID
- RTCM stream forwarded and logged

## Task Breakdown
- [ ] Repo structure + config file
- [ ] MAVLink connection + routing
- [ ] Telemetry store + heartbeat tracking
- [ ] RTK reader + injector
- [ ] Command dispatcher + guided control
- [ ] PySide6 UI
- [ ] Integration testing with 1-2 drones

## References
- docs/spec.md
- docs/design.md
- docs/dev_guide.md
- docs/task_breakdown.md
