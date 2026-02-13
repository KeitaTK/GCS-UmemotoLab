これまでの議論を踏まえ、**「ArduPilotの改造・カスタムメッセージの使用頻度が高い」**という要件に最適化した、最終的な地上局（GCS）システムの構成案をまとめます。

この構成は、ROS 2を使用せず、Raspberry Pi 5を**「高性能な通信ブリッジ（土管）」**として扱い、Windows上のPythonプログラムがあたかもFCと直結しているかのように振る舞う設計です。

---

### 1. システム全体像：Pure MAVLink構成

* **基本思想:** 複雑な変換処理（ROS化など）を廃止し、ArduPilotのネイティブ言語である「MAVLink」をそのまま地上局まで通す。
* **通信プロトコル:** MAVLink v2 over UDP/Wi-Fi
* **マルチドローン識別:** MAVLink System ID (`SYSID_THISMAV`) を使用

---

### 2. 機体側 (Drone Side) の構成

Raspberry Pi 5は、ArduPilotからのシリアルデータをWi-Fi（UDP）に変換して転送するだけの役割に徹します。

* **ハードウェア:**
* **FC:** Pixhawk 6C 等 (ArduPilot Custom Firmware)
* **Companion:** Raspberry Pi 5
* **接続:** FC ⇔ Raspi 5 は USBシリアル または UART(GPIO) で接続


* **ソフトウェア:**
* **OS:** Raspberry Pi OS (Lite版推奨)
* **コアソフト:** **`mavlink-router`** (C++製)


* **設定 (`main.conf`):**
* `[uart]` セクション: FCとの接続ポートを指定（例: `/dev/ttyAMA0`）
* `[udp]` セクション: 地上局PCのIPアドレス、またはブロードキャストアドレスへ向けてパケットを放出（例: `Endpoint = 0.0.0.0:14550`）



---

### 3. 地上局側 (GCS Side) の構成

Windows PCですべてのロジック（表示、制御、RTK配信）を処理します。

* **ハードウェア:**
* Windows 10/11 PC
* Wi-Fi接続


* **ソフトウェアスタック:**
* **言語:** Python 3.9 ～ 3.12
* **GUIライブラリ:** **PySide6** (Qt for Python)
* **通信ライブラリ:** **`pymavlink`**
* **RTKソース:** u-center (バックグラウンドで起動)


* **カスタム定義:**
* ArduPilotで追加したカスタムメッセージ定義（XML）から生成した `pymavlink` ライブラリを使用することで、独自データも即座に扱えます。



---

### 4. 機能別データフロー詳細

#### ① RTK補正情報の配信 (RTK Injection)

1. **u-center:** NTRIP Server/TCP Server機能で、ローカルポート（例: 5000）にRTCMデータを出力。
2. **GCS (Python):** `socket` でポート5000に接続し、データを受信。
3. **GCS (pymavlink):** 受信データを `GPS_RTCM_DATA` メッセージに変換。
4. **送信:** 全ドローン（または特定のSystem ID）に向けてUDP送信。
5. **FC:** 受け取ったRTCMデータを内部のGPSドライバに渡し、RTK Fixを実現。

#### ② テレメトリとデバッグ情報の受信

1. **FC:** `gcs().send_named_float("MY_DEBUG", val)` 等でデータを送信。
2. **Raspi:** `mavlink-router` がそのままUDPパケットとして転送。
3. **GCS (Python):**
* `connection.recv_match(type='NAMED_VALUE_FLOAT', blocking=False)` で受信。
* `msg.name == "MY_DEBUG"` を判別してグラフ化や表示を行う。
* `msg.get_srcSystem()` を見て、どのドローンからのデータかを辞書型配列などで振り分け。



#### ③ 機体制御 (Command & Control)

1. **GCS (GUI):** 「離陸」ボタン押下。
2. **GCS (Python):** 対象ドローンのSystem IDを指定してコマンド送信。
* 例: `master.mav.command_long_send(target_system, target_component, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, ...)`


3. **Guidedモード:**
* `SET_POSITION_TARGET_LOCAL_NED` メッセージなどを使い、XYZ座標や速度指令を送信。



---

### 5. この構成のメリット（あなたの要望に対する適合性）

1. **カスタム開発に最強:**
* ArduPilotのソースコードを変更しても、Raspi側の設定変更は一切不要。PC側のPythonスクリプトを書き換えるだけで対応完了です。


2. **デバッグが高速:**
* 生データがそのままPCに届くため、通信遅延や変換ミスによるトラブルシュートの手間がありません。


3. **複数台制御が容易:**
* System IDだけで管理できるため、ネットワーク設定がシンプルです（ポート番号を機体ごとに分ける必要すらありません）。


4. **既存GCSとの共存:**
* `mavlink-router` の設定で、自作GCSへのポートと同時に、Mission Plannerへのポートも開けておけば、開発中に「自作アプリの挙動」と「標準ツールの挙動」を同時に見比べることができます。



### 6. 開発のファーストステップ

まず最初にやるべきことは以下の通りです。

1. **Raspi 5:** `mavlink-router` をインストールし、PCへUDPパケットが飛ぶように設定する。
2. **Windows:** Pythonで以下のミニマムコードを動かし、接続確認をする。

```python
from pymavlink import mavutil

# UDPポート14550で待ち受け
master = mavutil.mavlink_connection('udpin:0.0.0.0:14550')

print("Waiting for heartbeat...")
while True:
    msg = master.recv_match(blocking=True)
    if not msg:
        continue
    
    # メッセージIDと送信元システムIDを表示
    if msg.get_type() == 'HEARTBEAT':
        print(f"Heartbeat from System ID: {msg.get_srcSystem()}")
    
    # カスタムデバッグ値の受信例
    if msg.get_type() == 'NAMED_VALUE_FLOAT':
        print(f"Debug Val from {msg.get_srcSystem()}: {msg.name} = {msg.value}")

```

このコードでドローンからのデータが見えれば、あとはQtでUIを作るフェーズに進めます。これが最も確実でリスクの少ない開発ルートです。