# Task Breakdown (MVP)

## Phase 1: Repo Setup
- Create folder structure (`app/`, `config/`, `docs/`)
- Add baseline config file
- Add logging configuration

## Phase 2: MAVLink Core
- Implement `MavlinkConnection` for UDP in/out
- Implement `MessageRouter` receive loop
- Implement `TelemetryStore` with per-system ID state
- Add heartbeat tracking

## Phase 3: RTK Injection
- Implement `RtcmReader` TCP client
- Implement `RtcmInjector` to send `GPS_RTCM_DATA`
- Add config flags for enable/disable

## Phase 4: Command and Control
- Implement `CommandDispatcher` for arm/disarm/takeoff/land
- Implement `GuidedControl` for NED setpoints
- Verify response handling

## Phase 5: UI
- Implement `MainWindow` with drone list and telemetry panels
- Add RTK status indicators
- Add debug value graphs for `NAMED_VALUE_FLOAT`

## Phase 6: Integration and Validation
- Run with one drone and verify telemetry
- Run with two drones and verify system ID routing
- Verify RTCM injection with u-center

## Definition of Done
- All acceptance criteria in spec are met
- Config file documented
- Logs show successful heartbeat and command sends
