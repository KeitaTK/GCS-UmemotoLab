import socket
import time

# 設定
HOST = '127.0.0.1'
PORT = 2101
# サーバーのリストにあった大文字の名前に合わせます
MOUNTPOINT = 'UBLOX_EVK_F9P'

def main():
    print(f"[INFO] {HOST}:{PORT} に接続し、/{MOUNTPOINT} を受信します...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10)
        try:
            s.connect((HOST, PORT))
            # サーバーが期待する「正しい」リクエスト形式
            # 最後に空行 (\r\n\r\n) を確実に入れます
            request = f"GET /{MOUNTPOINT} HTTP/1.0\r\nUser-Agent: NTRIP PythonClient\r\n\r\n"
            s.sendall(request.encode())
            
        except Exception as e:
            print(f"[ERROR] 接続失敗: {e}")
            return

        total_bytes = 0
        start_time = time.time()
        
        while True:
            try:
                data = s.recv(4096)
                if not data:
                    print("\n[INFO] サーバーから接続が終了されました。")
                    break
                
                # 最初の返答が「ICY 200 OK」ならデータ配信開始
                if total_bytes == 0:
                    print("--- サーバーからの返答 ---")
                    print(data.decode(errors='ignore')[:100])
                    print("------------------------")
                    if b"ICY 200 OK" in data:
                        print("[SUCCESS] ついにデータ受信が始まりました！")

                total_bytes += len(data)
                # 累計バイト数を更新表示
                print(f"\r受信中: 累計 {total_bytes} バイト", end="")
                
            except socket.timeout:
                print("\n[WARN] 待機中...")
                continue
            except KeyboardInterrupt:
                print("\n[INFO] 停止しました。")
                break

if __name__ == "__main__":
    main()