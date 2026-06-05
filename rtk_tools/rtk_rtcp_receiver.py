import argparse
import socket
import time


def build_request(mountpoint: str, user_agent: str) -> bytes:
    return (
        f"GET /{mountpoint} HTTP/1.0\r\n"
        f"User-Agent: {user_agent}\r\n"
        "\r\n"
    ).encode("ascii")


def split_header_and_payload(chunk: bytes) -> tuple[bytes, bytes]:
    if b"\r\n\r\n" in chunk:
        header, payload = chunk.split(b"\r\n\r\n", 1)
        return header, payload
    if b"\n\n" in chunk:
        header, payload = chunk.split(b"\n\n", 1)
        return header, payload
    return chunk, b""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NTRIPキャスターからRTCMを受信し、UDPで別PCへ転送します。"
    )
    parser.add_argument("--host", default="127.0.0.1", help="NTRIPキャスターのホスト")
    parser.add_argument("--port", type=int, default=2101, help="NTRIPキャスターポート")
    parser.add_argument(
        "--mountpoint",
        default="UBLOX_EVK_F9P",
        help="NTRIPマウントポイント名",
    )
    parser.add_argument(
        "--user-agent",
        default="NTRIP PythonClient",
        help="NTRIPリクエストのUser-Agent",
    )
    parser.add_argument(
        "--forward-host",
        default="127.0.0.1",
        help="転送先PCのIPアドレス",
    )
    parser.add_argument(
        "--forward-port",
        type=int,
        default=50010,
        help="転送先PCのUDPポート",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="受信タイムアウト秒")
    parser.add_argument("--chunk-size", type=int, default=4096, help="1回の受信バイト数")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(
        f"[INFO] {args.host}:{args.port} に接続し、/{args.mountpoint} を受信します..."
    )
    print(
        f"[INFO] 転送先: UDP {args.forward_host}:{args.forward_port}"
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ntrip_sock, socket.socket(
        socket.AF_INET, socket.SOCK_DGRAM
    ) as forward_sock:
        ntrip_sock.settimeout(args.timeout)
        try:
            ntrip_sock.connect((args.host, args.port))
            request = build_request(args.mountpoint, args.user_agent)
            ntrip_sock.sendall(request)
        except Exception as exc:
            print(f"[ERROR] 接続失敗: {exc}")
            return

        total_received = 0
        total_forwarded = 0
        start_time = time.time()
        header_checked = False

        while True:
            try:
                data = ntrip_sock.recv(args.chunk_size)
                if not data:
                    print("\n[INFO] サーバーから接続が終了されました。")
                    break

                if not header_checked:
                    header_checked = True
                    header, payload = split_header_and_payload(data)
                    header_preview = header.decode(errors="ignore")[:200]
                    print("--- サーバーからの返答 ---")
                    print(header_preview)
                    print("------------------------")

                    if b"200" not in header:
                        print("[ERROR] NTRIP接続に失敗しました。レスポンスを確認してください。")
                        break

                    print("[SUCCESS] RTCMデータ受信開始。転送を実行します。")
                    if payload:
                        forward_sock.sendto(payload, (args.forward_host, args.forward_port))
                        total_received += len(payload)
                        total_forwarded += len(payload)
                else:
                    forward_sock.sendto(data, (args.forward_host, args.forward_port))
                    total_received += len(data)
                    total_forwarded += len(data)

                elapsed = max(time.time() - start_time, 1e-6)
                rate = total_forwarded / elapsed
                print(
                    f"\r転送中: 受信 {total_received} bytes / 転送 {total_forwarded} bytes / {rate:.1f} Bps",
                    end="",
                )
            except socket.timeout:
                print("\n[WARN] 待機中...")
                continue
            except KeyboardInterrupt:
                print("\n[INFO] 停止しました。")
                break


if __name__ == "__main__":
    main()
