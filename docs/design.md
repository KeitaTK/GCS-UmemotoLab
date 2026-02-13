# GCS System Design (Detailed)

## 1. Architecture Overview
A Windows GCS application in Python (PySide6) communicates with ArduPilot via MAVLink v2 over UDP. The application handles:
- MAVLink receive/transmit
- RTK injection
- Telemetry aggregation
- UI display

### Data Flow
1. UDP inbound -> MAVLink decoder -> Telemetry store -> UI
2. UI command -> Command queue -> MAVLink encoder -> UDP outbound
3. RTCM TCP -> RTCM chunker -> MAVLink GPS_RTCM_DATA -> UDP outbound

## 2. Module Layout
```
app/
  __init__.py
  main.py
  config.py
  logging_config.py
  mavlink/
    __init__.py
    connection.py
    message_router.py
    telemetry_store.py
  rtk/
    __init__.py
    rtcm_reader.py
    rtcm_injector.py
  control/
    __init__.py
    command_dispatcher.py
    guided_control.py
  ui/
    __init__.py
    main_window.py
    widgets.py
  models/
    __init__.py
    drone_state.py
    enums.py
config/
  gcs.yml
```

## 3. Key Classes and Responsibilities
### 3.1 MAVLink
- `MavlinkConnection` (in `app/mavlink/connection.py`)
  - Open `udpin` and `udpout` endpoints
  - Reconnect on failure
- `MessageRouter` (in `app/mavlink/message_router.py`)
  - Read messages
  - Dispatch to telemetry store
- `TelemetryStore` (in `app/mavlink/telemetry_store.py`)
  - In-memory state per system ID
  - Thread-safe access (locks)

### 3.2 RTK
- `RtcmReader` (in `app/rtk/rtcm_reader.py`)
  - Connect to TCP source
  - Read RTCM bytes in chunks
- `RtcmInjector` (in `app/rtk/rtcm_injector.py`)
  - Convert to `GPS_RTCM_DATA`
  - Send to target system IDs

### 3.3 Control
- `CommandDispatcher` (in `app/control/command_dispatcher.py`)
  - Queue-based command sending
  - Ensure correct target system ID
- `GuidedControl` (in `app/control/guided_control.py`)
  - Build `SET_POSITION_TARGET_LOCAL_NED` messages

### 3.4 UI
- `MainWindow` (in `app/ui/main_window.py`)
  - List drones
  - Buttons for arm, takeoff, land
  - Telemetry graphs for named values

### 3.5 Models
- `DroneState` (in `app/models/drone_state.py`)
  - Holds latest heartbeat, position, and debug values

## 4. Concurrency Model
- Thread A: MAVLink receive loop (`MessageRouter.run`) using `threading.Thread`
- Thread B: RTCM read loop (`RtcmReader.run`) using `threading.Thread`
- Main Thread: Qt UI event loop
- No multiprocessing in MVP. CPU load is low and shared state is needed.

### Sync vs Async
- Use blocking reads in threads for UDP and TCP.
- UI updates via Qt signals to avoid cross-thread UI access.

## 5. Error Handling
- Reconnect with exponential backoff on socket errors.
- Drop malformed MAVLink packets; log errors.
- If RTCM source is unavailable, continue MAVLink operation.

## 6. Configuration Details
- `config/gcs.yml` fields:
  - `udp.listen_port: 14550`
  - `udp.broadcast: true|false`
  - `drones: { system_id: { ip, port, label } }`
  - `rtcm: { host, port, enabled }`
  - `telemetry: { named_value_filters, log_types }`

## 7. Extensibility
- Custom MAVLink XML: generate and place in `third_party/mavlink`.
- Add new telemetry widgets by subscribing to `TelemetryStore`.

## 8. Security
- Operate on closed Wi-Fi network.
- No external network exposure.

## 9. References
- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository
