# RTK注入 → MAVLink切断 調査記録

**日付**: 2026-07-06〜07  
**関連**: CRC修正タスク `4f058`, デバッグタスク `8cf9c`, ソケット分離タスク `5a7f1`

## 概要

GPS_RTCM_DATA (msgid=233) の CRC を修正（CRC_EXTRA=35 を追加）したところ、RTCM注入開始と同時にMAVLink通信が切断される現象が発生した。

## 時系列

1. **修正前**: `rtcm_injector.py` が手動で MAVLink v2 フレームを構築。CRC_EXTRA なし（＝CRC不正）。
   - Pixhawk が CRC 不一致でフレームを破棄 → RTCM は届かないが通信は正常 ✅

2. **CRC修正 (task 4f058)**: pymavlink `encode()+pack()` に置換。CRC_EXTRA 自動付与。
   - Pixhawk が CRC を正常検証 → RTCM を処理 → 通信断 ❌

3. **v1/v2 フレーム形式の検証 (task 8cf9c)**:
   - pymavlink v10 → v1 フレーム (0xFE) → 切れる
   - pymavlink v20 → v2 フレーム (0xFD) → 切れる
   - 手動 v2 + CRC_EXTRA → 切れる

4. **ソケット分離の検証 (task 5a7f1)**:
   - 送受信別ソケット → 切れる
   - Lock付き同一ソケット → 切れる
   - **完全別プロセス + 別ソケット** (`rtcm_injector_v2.py`) → 切れる

5. **sysid=255 での送信** → 切れる

## 検証結果まとめ

| 条件 | フレーム | CRC | ソケット | 結果 |
|------|---------|-----|---------|------|
| 修正前 | 手動v2 | 不正 | 同一 | ✅ OK |
| pymavlink v10 | v1(0xFE) | 正 | 同一 | ❌ 切断 |
| pymavlink v20 | v2(0xFD) | 正 | 同一 | ❌ 切断 |
| 手動v2+CRC_EXTRA | v2(0xFD) | 正 | 別プロセス | ❌ 切断 |
| sysid=255 | v2(0xFD) | 正 | 別プロセス | ❌ 切断 |

**共通点: CRCが正 → 切断。PixhawkがGPS_RTCM_DATAを実際に処理した結果、何かが起きている。**

## 推定原因

Pixhawk の GPS 構成が **DroneCAN** (`GPS 1: specified as DroneCAN1-125`) であることから：

```
GPS_RTCM_DATA(CRC正) → Pixhawk受信 → シリアルポートにRTCM転送
                                       ↓
                                  転送先がTELEM1(UART)と競合？
                                  MAVLinkストリームにRTCMバイトが混入
                                       ↓
                                  通信破綻
```

通常のシリアル接続GPSでは GPS_RTCM_DATA は GPS 用の UART に転送されるが、
DroneCAN GPS では転送先が異なり、TELEM1 と競合している可能性がある。

## 次のステップ

1. Pixhawk のパラメータを取得（別途用意したスクリプトで）
   ```bash
   # ラズパイで
   sudo systemctl stop mavlink-router
   python3 dump_params.py
   sudo systemctl start mavlink-router
   ```

2. 特に確認すべきパラメータ:
   - `GPS_TYPE` — DroneCANなら9
   - `SERIAL3_PROTOCOL`, `SERIAL4_PROTOCOL` — GPS用ポート設定
   - `GPS_INJECT_TO` — RTCM注入先ポート
   - `BRD_SER3_RTSCTS` などフロー制御

3. Mission Planner で GPS 設定を見直し、RTCM 注入パスを確認

## 関連ファイル

- `rtk_tools/rtcm_injector_v2.py` — 手動v2フレーム + CRC_EXTRA のスタンドアロン注入器
- `tests/test_rtcm_injection.py` — GPS_RTCM_DATA 単体テスト
- `/home/taki/Mavlink_raspi/RTK/dump_params.py` — パラメータダンプスクリプト
