import serial
from pyubx2 import UBXReader, RTCM3_PROTOCOL

# 設定（自分の環境に合わせてください）
PORT = 'COM6' 
BAUD = 115200

def main():
    print(f"--- RTCM3 解析モード開始 ({PORT}) ---")
    try:
        with serial.Serial(PORT, BAUD, timeout=1) as ser:
            # UBXReader を使い、プロトコルとして RTCM3 を指定します
            rtr = UBXReader(ser, protfilter=RTCM3_PROTOCOL)
            
            for (raw_data, parsed_data) in rtr:
                if parsed_data:
                    # RTCM3メッセージのID（1005, 1074など）を取得
                    # pyubx2の仕様により identity または msgID で取得できます
                    msg_id = parsed_data.identity
                    print(f"【解析成功】Message ID: {msg_id}")
                    
                    # 内容の表示
                    if msg_id == "1005":
                        print(f"  >>> [基準局座標] {parsed_data}")
                    elif "107" in msg_id: # 1074, 1077など
                        print(f"  >>> [GPS補正データ受信中]")
                    elif "108" in msg_id: # 1084, 1087など
                        print(f"  >>> [GLONASS補正データ受信中]")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main()