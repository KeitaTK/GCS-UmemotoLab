# GCSシステム仕様（詳細）

## 1. 目的
UDP経由でMAVLink v2を直接使用し、カスタムMAVLinkメッセージをサポートし、Windows上で複数のドローンの制御を可能にするArduPilot用のカスタムGCS（地上管制局）を構築します。

## 2. スコープ
### スコープ内
- Windows上でのMAVLink v2 UDP受信/送信。
- `GPS_RTCM_DATA`を使用したRTKインジェクション。
- `NAMED_VALUE_FLOAT`とカスタムメッセージを含むテレメトリー受信。
- `SYSID_THISMAV`による複数ドローンの識別。
- PySide6を使用した最小限のオペレーターUI。
- 設定駆動型のエンドポイントとシステムIDマッピング。

### スコープ外
- ROS 2統合。
- `mavlink-router`を超えたオンボード（Raspberry Pi）処理。
- Mission Plannerに相当するミッション計画UI。

## 3. 前提条件
- ドローン側：ArduPilot + UDPに転送する`mavlink-router`。
- カスタムMAVLink XMLが利用可能で、`pymavlink`の生成に使用される。
- Windows 10/11でPython 3.10+。

## 4. 機能要件
### 4.1 接続とルーティング
- GCSはデフォルトでUDPポート`14550`でリッスンします。
- GCSはシステムIDごとに設定された複数のエンドポイントに送信できます。
- GCSはハートビートを使用してドローンごとの接続ステータスを表示する必要があります。

### 4.2 テレメトリー
- 受信と表示：
  - `HEARTBEAT`
  - `NAMED_VALUE_FLOAT`
  - `SYS_STATUS`
  - `GLOBAL_POSITION_INT`
- カスタムMAVLinkメッセージ（生成された`pymavlink`）をサポート。
- テレメトリーはメモリに保存され、グラフ用のUIで利用可能。

### 4.3 コマンドと制御
- 選択されたシステムIDに基本コマンドを送信：
  - アーム/ディスアーム（`MAV_CMD_COMPONENT_ARM_DISARM`）
  - 離陸（`MAV_CMD_NAV_TAKEOFF`）
  - 着陸（`MAV_CMD_NAV_LAND`）
- `SET_POSITION_TARGET_LOCAL_NED`によるガイド制御。

### 4.4 RTKインジェクション
- RTCMストリーム用のローカルTCPポートに接続（デフォルト`5000`）。
- RTCMを`GPS_RTCM_DATA`にカプセル化し、選択されたシステムIDに送信。
- すべての既知のシステムIDへのブロードキャストをサポート。

### 4.5 ログ記録
- 受信したすべてのメッセージをログに記録（設定でタイプ別にフィルタリング）。
- エラー、再接続の試行、コマンド送信結果をログに記録。

## 5. 非機能要件
- UDP受信からUIアップデートまでの遅延：通常負荷時200ms未満。
- 再起動なしでUDPソースの損失時に再接続。
- 各10Hzテレメトリーで3台以上のドローンでの安定動作。

## 6. インターフェース
### 6.1 UDP MAVLink
- リスナー：`udpin:0.0.0.0:14550`（デフォルト）
- 発信：ドローンごとまたはブロードキャストの`udpout:<ip>:<port>`

### 6.2 RTCM TCP
- ローカルTCPサーバー：`127.0.0.1:5000`（デフォルト）

## 7. 設定
- ファイル：`config/gcs.yml`
- 含まれるもの：
  - UDPリッスンポート
  - 既知のドローン：システムIDからエンドポイント
  - RTCMホスト/ポート
  - テレメトリーフィルター

## 8. 受け入れ基準
- GCSは少なくとも1台のドローンのハートビートを表示します。
- `NAMED_VALUE_FLOAT`の値が表示され、更新されます。
- アーム/ディスアームコマンドが選択されたドローンに到達し、結果を報告します。
- RTCMストリームが転送され、少なくとも1台のドローンについてログに記録されます。

## 9. 参考資料
- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository
- https://docs.github.com/en/issues/tracking-your-work-with-issues/creating-an-issue
