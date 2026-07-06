### 2026-07-06 19:30: [RTCMログ保存機能]
- 問題: RTK補正情報（RTCMデータ）がArduPilotに送信されているがRTK Fixしない問題。送信データの内容を確認する手段がなかった。
- 調査: 既存コードを確認した結果、RTCM生データおよびMAVLink注入フレームのファイル保存機能が存在しないことが判明。
- 試行: `app/rtk_tools/rtcm_logger.py` に `RtcmLogger` クラスを新規作成。RTCM生データとMAVLink注入フレームの両方を、タイムスタンプ・長さ情報付きバイナリ形式で `logs/rtcm_raw_*.bin` / `logs/rtcm_injected_*.bin` に保存する機能を実装。
- 結果: `app/main.py` に組み込み完了。GCS起動時に自動でログ保存が開始される。60秒ごとに統計（メッセージタイプ別カウント、バイト数等）を表示。
- 備考: 保存されたバイナリは `pyrtcm` パッケージで解析可能。またArduPilot出力から `GPS 1: specified as DroneCAN1-125` が確認されており、DroneCAN GPSへのRTCM注入方法の調査が別途必要。