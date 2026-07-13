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

## Still Active (Not Moved)

- **`app/rtk_tools/rtcm_reader.py`** — Still used by the legacy MAVLink path for backward compatibility. Reduced scope under the new UART2 direct injection architecture.
- **`app/rtk_tools/rtcm_injector.py`** — Already deprecated (Task 6). Still imported by legacy code paths but marked with `DeprecationWarning`. Cannot be moved without updating all importers.

## Restoration

To restore any file to active use:

```bash
cp legacy/<filename> <original_location>
```
