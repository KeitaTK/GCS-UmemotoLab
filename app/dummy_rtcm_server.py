import socket
import time
import threading

def start_dummy_rtcm_server(host='127.0.0.1', port=15000):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)
    print(f"Dummy RTCM Server listening on {host}:{port}")

    def handle_client(conn, addr):
        print(f"Client connected: {addr}")
        try:
            while True:
                # 疑似的なRTCMデータを送信（数バイトのバイナリ）
                fake_rtcm_data = b'\xD3\x00\x13\x3E\xD0\x00\x03\x80\x00\x00\x00\x00\x00'
                conn.send(fake_rtcm_data)
                time.sleep(2)  # 2秒ごとに送信
        except (ConnectionResetError, BrokenPipeError):
            print(f"Client disconnected: {addr}")
        finally:
            conn.close()

    while True:
        try:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            print("\nShutting down RTCM server.")
            break

if __name__ == "__main__":
    start_dummy_rtcm_server()
