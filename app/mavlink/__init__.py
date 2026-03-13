"""
mavlink - MAVLink通信・RTK補正・機体制御モジュール

このパッケージは、ArduPilot（Pixhawk）との通信・制御に関する機能を提供します。

Submodules
----------

connection : MAVLink接続管理
    - UDP/Serialポート管理
    - データ送受信
    
message_router : MAVLinkメッセージ中継
    - メッセージ解析・分類
    - コールバック登録
    
telemetry_store : テレメトリーデータ保存
    - 複数ドローンのテレメトリー管理
    - リアルタイムデータ取得
    
command_dispatcher : ドローン制御コマンド
    - アーム/ディスアーム
    - 離陸/着陸コマンド
    
guided_control : ガイドモード制御
    - 位置指定飛行
    - 速度制御
    
rtcm_reader : RTK補正データ受信
    - TCP/Ntripソケット接続
    - RTCMメッセージ解析
    
rtcm_injector : RTK補正データ送信
    - GPS_RTCM_DATA メッセージ生成
    - 大容量データチャンク化

Examples
--------

基本的な使用例:

>>> from mavlink.connection import MavlinkConnection
>>> from mavlink.message_router import MessageRouter
>>> from mavlink.telemetry_store import TelemetryStore
>>> 
>>> # 接続と初期化
>>> mav_conn = MavlinkConnection("config/gcs.yml")
>>> telemetry_store = TelemetryStore()
>>> router = MessageRouter(mav_conn, telemetry_store)
>>> router.start()
>>> 
>>> # テレメトリー取得
>>> heartbeat = telemetry_store.get_message(system_id=1, msg_name='HEARTBEAT')
>>> position = telemetry_store.get_message(system_id=1, msg_name='GLOBAL_POSITION_INT')

"""
