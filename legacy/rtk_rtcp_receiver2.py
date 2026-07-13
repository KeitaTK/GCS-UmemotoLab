import argparse
import socket

import serial
from pyubx2 import RTCM3_PROTOCOL, UBXReader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="シリアルからRTCM3を読み取り、解析結果表示とUDP転送を行います。"
    )
    parser.add_argument(
        "--port",
        default="COM8",
        help="シリアルポート (Windows: COM8, Linux: /dev/ttyUSB0 など)",
    )
    parser.add_argument("--baud", type=int, default=115200, help="シリアルボーレート")
    parser.add_argument("--timeout", type=float, default=1.0, help="シリアルタイムアウト秒")
    parser.add_argument(
        "--forward-host",
        default="127.0.0.1",
        help="転送先PCのIPアドレス",
    )
    parser.add_argument(
        "--forward-port",
        type=int,
        default=50011,
        help="転送先PCのUDPポート",
    )
    parser.add_argument(
        "--no-forward",
        action="store_true",
        help="UDP転送を無効化して解析表示のみ行う",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"--- RTCM3 解析モード開始 ({args.port}, {args.baud}bps) ---")
    if args.no_forward:
        print("[INFO] UDP転送: 無効")
    else:
        print(f"[INFO] UDP転送先: {args.forward_host}:{args.forward_port}")

    packet_count = 0
    forwarded_bytes = 0

    try:
        with serial.Serial(args.port, args.baud, timeout=args.timeout) as ser, socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM
        ) as udp_sock:
            rtr = UBXReader(ser, protfilter=RTCM3_PROTOCOL)

            for raw_data, parsed_data in rtr:
                if not raw_data:
                    continue

                packet_count += 1
                if not args.no_forward:
                    udp_sock.sendto(raw_data, (args.forward_host, args.forward_port))
                    forwarded_bytes += len(raw_data)

                if parsed_data:
                    msg_id = parsed_data.identity
                    print(f"[RTCM] Message ID: {msg_id}")
                    if msg_id == "1005":
                        print(f"  >>> [基準局座標] {parsed_data}")
                    elif "107" in msg_id:
                        print("  >>> [GPS補正データ受信中]")
                    elif "108" in msg_id:
                        print("  >>> [GLONASS補正データ受信中]")

                if packet_count % 20 == 0:
                    print(
                        f"[INFO] 受信パケット数: {packet_count}, 転送バイト数: {forwarded_bytes}"
                    )

    except KeyboardInterrupt:
        print("\n[INFO] 停止しました。")
    except Exception as exc:
        print(f"エラーが発生しました: {exc}")


if __name__ == "__main__":
    main()
