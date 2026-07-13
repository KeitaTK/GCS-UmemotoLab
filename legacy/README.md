# Legacy RTCM Files

These files were part of the **old MAVLink GPS_RTCM_DATA injection pipeline**:

```
  Base Station → TCP → rtcm_reader.py → rtcm_injector.py → MAVLink GPS_RTCM_DATA → Pixhawk → DroneCAN → F9P
```

They have been moved here for reference and potential rollback. They are **not used** by the current architecture.

## Replacement Architecture

The current pipeline uses **UART2 direct injection**:

```
  Base Station → NTRIP/TCP → rtk_forwarder (serial output) → UART2 → F9P
```

See: [`docs/05-implementation/rtk_direct_uart2_injection_plan.md`](../docs/05-implementation/rtk_direct_uart2_injection_plan.md)

---

## Files

| File | Original Location | Description | Superseded By |
|------|------------------|-------------|---------------|
| `test_rtcm.py` | `app/rtk_tools/test_rtcm.py` | Empty test placeholder (0 bytes) | — |
| `dummy_rtcm_server.py` | `rtk_tools/dummy_rtcm_server.py` | Dummy TCP server that sends fake RTCM3 frames for testing | `rtk_forwarder_service.py` |
| `rtk_rtcp_receiver.py` | `rtk_tools/rtk_rtcp_receiver.py` | NTRIP caster → UDP RTCM forwarding client | `rtk_forwarder_service.py` |
| `rtk_rtcp_receiver2.py` | `rtk_tools/rtk_rtcp_receiver2.py` | Serial port RTCM3 parser with UDP forwarding | `rtk_forwarder_service.py` |
| `backend_minimal.py` | `rtk_tools/backend_minimal.py` | Minimal serial MAVLink receiver for Raspberry Pi with RTK/RTCM3 support; zero external dependencies | `rtk_forwarder_service.py` |
| `command_sender.py` | `rtk_tools/command_sender.py` | MAVLink command sender for Pixhawk via serial port (stdlib only) | — |
| `standalone_obs.py` | `rtk_tools/standalone_obs.py` | Standalone GPS observation script for F9P; captures NMEA data and outputs best-Fix average coordinates | — |
| `test_rtk_integration.py` | `rtk_tools/test_rtk_integration.py` | Integration test verifying RTCM injection flow from base station to Pixhawk | — |
| `backend_server.py` | `rtk_tools/backend_server.py` | Headless GCS backend server; forwards MAVLink from Pixhawk to remote GCS over TCP | `backend_minimal.py` |
| `rtk_data_collector.py` | `rtk_tools/rtk_data_collector.py` | Dual data collector for u-blox base station + Pixhawk rover; real-time error analysis with CSV/JSON output | — |
| `rtk_base_station.py` | `rtk_tools/rtk_base_station.py` | RTK base station v1; receives RTCM from ublox F9P via serial and distributes via TCP/UDP | `rtk_base_station_v2.py` |

## Still Active (Not Moved)

- **`app/rtk_tools/rtcm_reader.py`** — Still used by the legacy MAVLink path for backward compatibility. Reduced scope under the new UART2 direct injection architecture.
- **`app/rtk_tools/rtcm_injector.py`** — Already deprecated (Task 6). Still imported by legacy code paths but marked with `DeprecationWarning`. Cannot be moved without updating all importers.

## Restoration

To restore any file to active use:

```bash
cp legacy/<filename> <original_location>
```
