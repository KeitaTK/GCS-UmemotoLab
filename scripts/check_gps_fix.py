#!/usr/bin/env python3
"""
GPS Fix 状態診断スクリプト
u-blox と Pixhawk の GPS が Fix しているか調査します。

【fix_type 一覧】
  0: NO_GPS       - GPS未検出
  1: NO_FIX       - 衛星捕捉中（Fix未成立）
  2: 2D_FIX       - 2D測位（水平のみ）
  3: 3D_FIX       - 3D測位（水平＋高度）
  4: DGPS         - ディファレンシャルGPS
  5: RTK_FLOAT    - RTK Float（精度数十cm）
  6: RTK_FIXED    - RTK Fixed（精度1-3cm）★ 最高精度

【使用例】
  python scripts/check_gps_fix.py
  python scripts/check_gps_fix.py --config gcs_drone.yml
  python scripts/check_gps_fix.py --ublox /dev/tty.usbmodem123
  python scripts/check_gps_fix.py --duration 60
"""

import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("GPS-Check")

FIX_TYPE_NAMES = {
    0: "NO_GPS", 1: "NO_FIX", 2: "2D_FIX", 3: "3D_FIX",
    4: "DGPS", 5: "RTK_FLOAT", 6: "RTK_FIXED",
    7: "STATIC", 8: "PPP",
}

FIX_TYPE_ICONS = {
    0: "\u274c", 1: "\u23f3", 2: "\U0001f7e1", 3: "\U0001f7e0",
    4: "\U0001f535", 5: "\U0001f7e2", 6: "\u2b50",
    7: "\u23f8", 8: "\U0001f537",
}


def resolve_config_path(config_name=None):
    config_dir = Path(__file__).parent.parent / "config"
    if config_name:
        path = config_dir / config_name
        if not path.suffix:
            path = path.with_suffix(".yml")
    else:
        path = config_dir / "gcs.yml"
    return str(path.resolve())


def check_pixhawk_gps(config_path, duration_sec=30):
    """Pixhawk GPS 状態を MAVLink 経由でチェック。"""
    result = {
        'connected': False, 'fix_type': None, 'fix_name': 'N/A',
        'satellites': None, 'lat': None, 'lon': None, 'alt': None,
        'hdop': None, 'messages_received': 0, 'system_id': None,
    }
    try:
        from app.mavlink.connection import MavlinkConnection
        logger.info(f"Pixhawk MAVLink接続を試行中... (config: {config_path})")
        conn = MavlinkConnection(config_path)
        if not hasattr(conn, 'mav'):
            logger.error("MAVLink接続オブジェクトが生成できませんでした")
            return result
        result['connected'] = True
        logger.info(f"✓ MAVLink 接続確立（{conn.connection_type}）")
        if conn.connection_type == 'serial':
            logger.info(f"  シリアルポート: {conn.serial_port} @ {conn.serial_baudrate} bps")

        start_time = time.time()
        logger.info(f"{'='*60}")
        logger.info(f"GPSデータ受信開始（{duration_sec}秒間）...")
        logger.info(f"{'='*60}")
        last_report_time = start_time

        while time.time() - start_time < duration_sec:
            try:
                msg = conn.mav.recv_match(timeout=1.0)
                if not msg:
                    continue
                msg_type = msg.get_type()
                system_id = msg.get_srcSystem()

                if msg_type == 'HEARTBEAT' and not result['system_id']:
                    result['system_id'] = system_id
                    logger.info(f"✓ Pixhawk (SysID={system_id}) 検出 (HEARTBEAT)")

                elif msg_type == 'GPS_RAW_INT':
                    result['messages_received'] += 1
                    fix_type = getattr(msg, 'fix_type', -1)
                    num_sats = getattr(msg, 'satellites_visible', 0)
                    lat = getattr(msg, 'lat', 0) / 1e7
                    lon = getattr(msg, 'lon', 0) / 1e7
                    alt = getattr(msg, 'alt', 0) / 1000.0
                    eph = getattr(msg, 'eph', 99999) / 100.0

                    result['fix_type'] = fix_type
                    result['fix_name'] = FIX_TYPE_NAMES.get(fix_type, f"UNKNOWN({fix_type})")
                    result['satellites'] = num_sats
                    result['lat'] = lat
                    result['lon'] = lon
                    result['alt'] = alt
                    result['hdop'] = eph

                    now = time.time()
                    if now - last_report_time >= 5:
                        icon = FIX_TYPE_ICONS.get(fix_type, "❓")
                        logger.info(
                            f"{icon} Fix={fix_type}({result['fix_name']})  "
                            f"Sats={num_sats}  Lat={lat:.6f}  Lon={lon:.6f}  "
                            f"Alt={alt:.2f}m  HDOP={eph:.2f}"
                        )
                        last_report_time = now
            except Exception as e:
                logger.debug(f"受信エラー: {e}")
                continue

        # 最終結果
        elapsed = time.time() - start_time
        logger.info(f"\n{'='*60}")
        logger.info(f"【Pixhawk GPS 診断結果】（{elapsed:.0f}秒間）")
        logger.info(f"{'='*60}")
        if result['system_id']:
            logger.info(f"  System ID:     {result['system_id']}")
        else:
            logger.warning("  ⚠ PixhawkからのHEARTBEAT未受信")
        logger.info(f"  GPS メッセージ受信数: {result['messages_received']}")

        if result['fix_type'] is not None:
            fix = result['fix_type']
            icon = FIX_TYPE_ICONS.get(fix, "❓")
            logger.info(f"  Fix Type:      {icon} {fix} ({result['fix_name']})")
            if fix >= 6:
                logger.info("  ✅ GPS状態: 最高精度！RTK Fixed 達成！")
            elif fix >= 5:
                logger.info("  ✅ GPS状態: RTK Float（高精度）")
            elif fix >= 3:
                logger.info("  ⚠ GPS状態: 3D Fix済み。RTK補正待ち")
            elif fix >= 2:
                logger.info("  ⚠ GPS状態: 2D Fixのみ（高度未確定）")
            elif fix == 1:
                logger.info("  ❌ GPS状態: No Fix - まだ衛星を捕捉できていません")
                logger.info("     → 屋外の開けた場所に移動してください")
            else:
                logger.info("  ❌ GPS状態: GPSモジュール未検出")
            logger.info(f"  衛星数:        {result['satellites']}")
            logger.info(f"  HDOP:          {result['hdop']:.2f} m")
            logger.info(f"  緯度:          {result['lat']:.6f}")
            logger.info(f"  経度:          {result['lon']:.6f}")
            logger.info(f"  高度(MSL):     {result['alt']:.2f} m")
        else:
            logger.warning("  ❌ GPS_RAW_INTメッセージ未受信")
            logger.info("     → PixhawkにGPSモジュールが接続されているか確認")

        # 推奨アクション
        logger.info(f"\n{'='*60}")
        logger.info("【推奨アクション】")
        logger.info(f"{'='*60}")
        fix = result['fix_type']
        if fix is None or fix <= 1:
            logger.info("  1. 屋外の開けた場所に移動")
            logger.info("  2. GPSモジュールの接続ケーブルを確認")
            logger.info("  3. Pixhawkの電源再投入")
            if result['system_id'] is None:
                logger.info("  4. PixhawkとPCのUSB/シリアル接続を確認")
        elif fix == 2:
            logger.info("  1. より広い空が見える場所に移動")
        elif fix in (3, 4):
            logger.info("  1. RTK補正を有効にする (rtcm_enabled: true)")
            logger.info("  2. rtk_base_station_v2.py を起動")
        elif fix == 5:
            logger.info("  1. RTK Float → RTK Fixed への収束を待つ（通常1-3分）")
        elif fix >= 6:
            logger.info("  ✅ 飛行可能！RTK Fixed達成")
        return result
    except ImportError as e:
        logger.error(f"必要なモジュールがありません: {e}")
        return result
    except Exception as e:
        logger.error(f"Pixhawk GPSチェックエラー: {e}")
        return result


def check_ublox_gps(serial_port, baudrate=38400, duration_sec=15):
    """u-blox GPS 状態をシリアルポート経由で直接確認。"""
    result = {
        'connected': False, 'fix_quality': None, 'satellites': None,
        'lat': None, 'lon': None, 'alt': None, 'messages': [],
    }
    try:
        import serial
    except ImportError:
        logger.error("pyserial がインストールされていません。pip install pyserial")
        return result
    try:
        logger.info(f"\nu-blox GPS シリアル接続を試行中... ({serial_port} @ {baudrate})")
        ser = serial.Serial(serial_port, baudrate, timeout=1.0)
        result['connected'] = True
        logger.info(f"✓ u-blox 接続完了: {serial_port}")
        start_time = time.time()
        logger.info(f"u-blox NMEA受信開始（{duration_sec}秒間）...")
        while time.time() - start_time < duration_sec:
            try:
                line = ser.readline().decode('ascii', errors='ignore').strip()
                if not line:
                    continue
                result['messages'].append(line)
                if line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                    parts = line.split(',')
                    if len(parts) >= 10:
                        try:
                            fix_quality = int(parts[6]) if parts[6] else 0
                            num_sats = int(parts[7]) if parts[7] else 0
                            lat_str, lat_dir = parts[2], parts[3]
                            lon_str, lon_dir = parts[4], parts[5]
                            alt_str = parts[9]
                            if lat_str and lon_str:
                                lat_dd = float(lat_str[:2]) + float(lat_str[2:]) / 60.0
                                if lat_dir == 'S':
                                    lat_dd = -lat_dd
                                lon_dd = float(lon_str[:3]) + float(lon_str[3:]) / 60.0
                                if lon_dir == 'W':
                                    lon_dd = -lon_dd
                                result['lat'] = lat_dd
                                result['lon'] = lon_dd
                            if alt_str:
                                result['alt'] = float(alt_str)
                            result['fix_quality'] = fix_quality
                            result['satellites'] = num_sats
                            fix_names = {0: "No Fix", 1: "GPS Fix", 2: "DGPS Fix",
                                         4: "RTK Fixed", 5: "RTK Float"}
                            fix_name = fix_names.get(fix_quality, f"Unknown({fix_quality})")
                            icon = FIX_TYPE_ICONS.get(fix_quality, "❓")
                            logger.info(
                                f"{icon} u-blox Fix={fix_quality}({fix_name})  "
                                f"Sats={num_sats}  "
                                f"Lat={result['lat']:.6f}  Lon={result['lon']:.6f}"
                            )
                        except (ValueError, IndexError) as e:
                            logger.debug(f"GGA parse error: {e}")
            except Exception as e:
                logger.debug(f"u-blox read error: {e}")
        ser.close()
        logger.info(f"\n{'='*60}")
        logger.info("【u-blox GPS 診断結果】")
        logger.info(f"{'='*60}")
        if result['fix_quality'] is not None:
            quality = result['fix_quality']
            if quality == 0:
                logger.info("  ❌ Fix状態: No Fix")
            elif quality == 1:
                logger.info("  ✅ Fix状態: GPS Fix（標準精度）")
            elif quality == 2:
                logger.info("  ✅ Fix状態: DGPS Fix（高精度）")
            elif quality == 4:
                logger.info("  ⭐ Fix状態: RTK Fixed（1-3cm）")
            elif quality == 5:
                logger.info("  ✅ Fix状態: RTK Float（数十cm）")
        else:
            logger.warning("  NMEA $GPGGA 未受信")
        logger.info(f"  衛星数:         {result['satellites']}")
        logger.info(f"  総NMEAメッセージ数: {len(result['messages'])}")
        return result
    except Exception as e:
        logger.error(f"u-blox GPSチェックエラー: {e}")
        return result


def print_summary(pixhawk_result, ublox_result=None):
    """総合サマリーを表示"""
    print(f"\n{'='*60}")
    print(f"  GPS Fix 診断 総合サマリー")
    print(f"{'='*60}")
    print(f"\n  [Pixhawk GPS]")
    if pixhawk_result.get('connected'):
        if pixhawk_result.get('fix_type') is not None:
            fix = pixhawk_result['fix_type']
            icon = FIX_TYPE_ICONS.get(fix, "❓")
            sats = pixhawk_result['satellites']
            status = "✅ Fix成立！" if fix >= 2 else "❌ 未Fix"
            print(f"    {icon} Fix: {pixhawk_result['fix_name']}  |  衛星数: {sats}  |  {status}")
            if fix >= 6:
                print(f"    🎉 RTK Fixed 達成！飛行可能です")
        else:
            print(f"    ⚠ GPS_RAW_INT 未受信")
    else:
        print(f"    ❌ Pixhawk に接続できません")

    if ublox_result:
        print(f"\n  [u-blox GPS]")
        if ublox_result.get('connected'):
            quality = ublox_result.get('fix_quality')
            if quality is not None:
                fix_names = {0: "No Fix", 1: "GPS Fix", 2: "DGPS Fix",
                             4: "RTK Fixed", 5: "RTK Float"}
                name = fix_names.get(quality, f"Unknown({quality})")
                icon = FIX_TYPE_ICONS.get(quality, "❓")
                status = "✅ Fix成立！" if quality >= 1 else "❌ 未Fix"
                print(f"    {icon} Fix: {name}  |  衛星数: {ublox_result['satellites']}  |  {status}")
            else:
                print(f"    ⚠ NMEA未受信")
        else:
            print(f"    ❌ u-blox に接続できません")
    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="GPS Fix 状態診断ツール - u-blox & Pixhawk GPSチェック",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  %(prog)s                                    # Pixhawk GPSチェック（30秒）
  %(prog)s --config gcs_drone.yml             # ドローン設定でチェック
  %(prog)s --duration 60                      # 60秒間監視
  %(prog)s --ublox /dev/tty.usbmodem212201    # u-bloxも同時チェック
  %(prog)s --ublox COM3 --ublox-baud 115200   # Windows + u-blox
        """
    )
    parser.add_argument(
        '--config', '-c', type=str, default=None,
        help='設定ファイル名 (config/ 以下のファイル名、デフォルト: gcs.yml)'
    )
    parser.add_argument(
        '--duration', '-d', type=int, default=30,
        help='GPSデータ受信時間（秒、デフォルト: 30）'
    )
    parser.add_argument(
        '--ublox', '-u', type=str, default=None,
        help='u-blox GPS のシリアルポート (/dev/tty.usbmodemXXX または COM3)'
    )
    parser.add_argument(
        '--ublox-baud', type=int, default=38400,
        help='u-blox のボーレート（デフォルト: 38400）'
    )
    parser.add_argument(
        '--skip-pixhawk', action='store_true',
        help='Pixhawk GPSチェックをスキップ'
    )

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  GPS Fix 診断ツール")
    print(f"  時刻: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    pixhawk_result = {}
    ublox_result = None

    if not args.skip_pixhawk:
        config_path = resolve_config_path(args.config)
        pixhawk_result = check_pixhawk_gps(config_path, duration_sec=args.duration)
    else:
        print("Pixhawk GPSチェック: スキップ")

    if args.ublox:
        ublox_result = check_ublox_gps(
            serial_port=args.ublox,
            baudrate=args.ublox_baud,
            duration_sec=args.duration
        )

    if pixhawk_result or ublox_result:
        print_summary(pixhawk_result, ublox_result)


if __name__ == '__main__':
    main()
