#!/usr/bin/env python3
"""
PHASE C: RTK統合テスト・検証スクリプト
- 1台ドローン：テレメトリー検証
- 2台ドローン：System ID ルーティング検証
- u-center連携：RTCM注入検証
"""

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'app'))

from mavlink.connection import MavlinkConnection
from config_loader import resolve_config_path
import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class SingleDroneTestValidator:
    """1台ドローンテスト検証"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.logger = logging.getLogger("SingleDroneTest")
        self.stats = {
            'heartbeats_received': 0,
            'telemetry_messages': 0,
            'rtcm_frames_received': 0,
            'gps_fix_achieved': False,
            'system_id': None,
            'start_time': None,
            'last_heartbeat': None
        }
    
    def run(self, duration_sec: int = 30) -> bool:
        """1台ドローン検証を実行"""
        self.logger.info("=" * 70)
        self.logger.info("【テスト1】1台ドローン検証 - テレメトリー受信")
        self.logger.info("=" * 70)
        
        try:
            # MAVLink 接続
            self.logger.info(f"設定ファイル: {self.config_path}")
            conn = MavlinkConnection(self.config_path)
            self.logger.info("✓ MAVLink 接続初期化完了")
            
            # テレメトリー受信ループ
            self.stats['start_time'] = time.time()
            self.logger.info(f"テレメトリー受信開始（{duration_sec}秒間）...")
            
            while time.time() - self.stats['start_time'] < duration_sec:
                try:
                    # メッセージ受信（タイムアウト1秒）
                    if hasattr(conn, 'mav'):
                        msg = conn.mav.recv_match(timeout=1)
                        if not msg:
                            continue
                        
                        msg_type = msg.get_type()
                        
                        # HEARTBEAT メッセージ処理
                        if msg_type == 'HEARTBEAT':
                            system_id = msg.get_srcSystem()
                            if not self.stats['system_id']:
                                self.stats['system_id'] = system_id
                                self.logger.info(f"✓ Drone {system_id} 検出 (HEARTBEAT)")
                            
                            self.stats['heartbeats_received'] += 1
                            self.stats['last_heartbeat'] = time.time()
                        
                        # GPS_RAW_INT メッセージ処理
                        elif msg_type == 'GPS_RAW_INT':
                            self.stats['telemetry_messages'] += 1
                            fix_type = msg.fix_type if hasattr(msg, 'fix_type') else 0
                            
                            if fix_type == 4:  # GPS RTK Fix
                                self.stats['gps_fix_achieved'] = True
                                self.logger.info(f"  ✓ GPS RTK Fix 達成！")
                            elif fix_type == 3:  # DGPS
                                self.logger.info(f"  • DGPS Fix (精度改善中...)")
                            else:
                                self.logger.debug(f"  GPS fix_type: {fix_type}")
                        
                        # SYS_STATUS メッセージ処理
                        elif msg_type == 'SYS_STATUS':
                            self.stats['telemetry_messages'] += 1
                        
                        # その他メッセージ
                        else:
                            self.stats['telemetry_messages'] += 1
                    
                    time.sleep(0.1)
                
                except Exception as e:
                    self.logger.debug(f"メッセージ処理エラー: {e}")
                    continue
            
            # テスト結果評価
            elapsed = time.time() - self.stats['start_time']
            
            self.logger.info(f"\n【受信統計（{elapsed:.1f}秒間）】")
            self.logger.info(f"  HEARTBEATs受信: {self.stats['heartbeats_received']}")
            self.logger.info(f"  テレメトリメッセージ: {self.stats['telemetry_messages']}")
            self.logger.info(f"  System ID: {self.stats['system_id']}")
            self.logger.info(f"  GPS RTK Fix: {'達成' if self.stats['gps_fix_achieved'] else '未達成'}")
            
            # 合格条件
            passed = (
                self.stats['heartbeats_received'] >= 3 and
                self.stats['system_id'] is not None
            )
            
            if passed:
                self.logger.info("✓ テスト1 PASSED（1台ドローン検証成功）\n")
            else:
                self.logger.warning("✗ テスト1 FAILED（ドローン検出失敗）\n")
            
            return passed
        
        except Exception as e:
            self.logger.error(f"テスト1 エラー: {e}", exc_info=True)
            return False


class MultiDroneRoutingValidator:
    """2台ドローンルーティング検証"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.logger = logging.getLogger("MultiDroneTest")
        self.drones = {}  # {system_id: stats}
        self.stats = {
            'total_heartbeats': 0,
            'unique_systems': set(),
            'start_time': None
        }
    
    def run(self, duration_sec: int = 30, expected_drones: int = 2) -> bool:
        """2台ドローン検証を実行"""
        self.logger.info("=" * 70)
        self.logger.info(f"【テスト2】{expected_drones}台ドローン検証 - System ID ルーティング")
        self.logger.info("=" * 70)
        
        try:
            self.logger.info(f"設定ファイル: {self.config_path}")
            conn = MavlinkConnection(self.config_path)
            self.logger.info("✓ MAVLink 接続初期化完了")
            
            self.stats['start_time'] = time.time()
            self.logger.info(f"マルチドローン受信開始（{duration_sec}秒間）...\n")
            
            while time.time() - self.stats['start_time'] < duration_sec:
                try:
                    if hasattr(conn, 'mav'):
                        msg = conn.mav.recv_match(timeout=1)
                        if not msg:
                            continue
                        
                        if msg.get_type() == 'HEARTBEAT':
                            system_id = msg.get_srcSystem()
                            component_id = msg.get_srcComponent()
                            
                            self.stats['total_heartbeats'] += 1
                            self.stats['unique_systems'].add(system_id)
                            
                            # ドローンごとの統計
                            if system_id not in self.drones:
                                self.drones[system_id] = {
                                    'count': 0,
                                    'first_seen': time.time(),
                                    'component_id': component_id
                                }
                                self.logger.info(f"✓ Drone {system_id} 検出 (component: {component_id})")
                            
                            self.drones[system_id]['count'] += 1
                    
                    time.sleep(0.1)
                
                except Exception as e:
                    self.logger.debug(f"メッセージ処理エラー: {e}")
                    continue
            
            # テスト結果評価
            elapsed = time.time() - self.stats['start_time']
            
            self.logger.info(f"\n【ルーティング統計（{elapsed:.1f}秒間）】")
            self.logger.info(f"  総HEARTBEAT数: {self.stats['total_heartbeats']}")
            self.logger.info(f"  検出ドローン数: {len(self.drones)}")
            
            for system_id, drone_stats in sorted(self.drones.items()):
                self.logger.info(f"  Drone {system_id}: {drone_stats['count']} HBs")
            
            # 合格条件
            passed = (
                len(self.drones) >= expected_drones and
                all(drone['count'] >= 3 for drone in self.drones.values())
            )
            
            if passed:
                self.logger.info(f"✓ テスト2 PASSED（{expected_drones}台ドローン検出成功）\n")
            else:
                self.logger.warning(f"✗ テスト2 FAILED（期待: {expected_drones}台、検出: {len(self.drones)}台）\n")
            
            return passed
        
        except Exception as e:
            self.logger.error(f"テスト2 エラー: {e}", exc_info=True)
            return False


class RtcmInjectionValidator:
    """RTCM注入検証"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.logger = logging.getLogger("RtcmValidation")
        self.stats = {
            'rtcm_enabled': False,
            'rtcm_host': None,
            'rtcm_port': None,
            'gps_fix_improvements': 0
        }
    
    def run(self) -> bool:
        """RTCM注入設定検証"""
        self.logger.info("=" * 70)
        self.logger.info("【テスト3】RTCM注入設定検証")
        self.logger.info("=" * 70)
        
        try:
            # 設定ファイル読み込み
            with open(self.config_path) as f:
                config = yaml.safe_load(f)
            
            self.stats['rtcm_enabled'] = config.get('rtcm_enabled', False)
            self.stats['rtcm_host'] = config.get('rtcm_host', 'N/A')
            self.stats['rtcm_port'] = config.get('rtcm_tcp_port', 'N/A')
            
            self.logger.info(f"\n【RTCM設定確認】")
            self.logger.info(f"  RTCM有効: {self.stats['rtcm_enabled']}")
            self.logger.info(f"  RTCMホスト: {self.stats['rtcm_host']}")
            self.logger.info(f"  RTCMポート: {self.stats['rtcm_port']}")
            
            if not self.stats['rtcm_enabled']:
                self.logger.warning("  ⚠ RTCM は無効です")
                self.logger.info("  → u-center で有効化してください")
                return False
            
            # 接続テスト
            import socket
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((self.stats['rtcm_host'], self.stats['rtcm_port']))
                sock.close()
                
                if result == 0:
                    self.logger.info(f"  ✓ RTCM接続可能: {self.stats['rtcm_host']}:{self.stats['rtcm_port']}")
                    self.logger.info("✓ テスト3 PASSED（RTCM注入設定OK）\n")
                    return True
                else:
                    self.logger.warning(f"  ✗ RTCM接続不可")
                    self.logger.warning("  → PC側 rtk_base_station.py が起動しているか確認")
                    return False
            
            except Exception as e:
                self.logger.error(f"接続エラー: {e}")
                return False
        
        except Exception as e:
            self.logger.error(f"テスト3 エラー: {e}", exc_info=True)
            return False


def main():
    """PHASE C 統合テスト実行"""
    logger.info("\n" + "=" * 70)
    logger.info("PHASE C: RTK統合テスト・検証スイート")
    logger.info("=" * 70 + "\n")
    
    config_path = resolve_config_path()
    results = {}
    
    # テスト1: 1台ドローン検証
    try:
        validator1 = SingleDroneTestValidator(config_path)
        results["1台ドローン検証"] = validator1.run(duration_sec=30)
    except Exception as e:
        logger.error(f"テスト1 失敗: {e}")
        results["1台ドローン検証"] = False
    
    # テスト2: 2台ドローン検証（オプション）
    try:
        validator2 = MultiDroneRoutingValidator(config_path)
        results["2台ドローン検証"] = validator2.run(duration_sec=30, expected_drones=2)
    except Exception as e:
        logger.error(f"テスト2 失敗: {e}")
        results["2台ドローン検証"] = False
    
    # テスト3: RTCM注入設定検証
    try:
        validator3 = RtcmInjectionValidator(config_path)
        results["RTCM注入設定"] = validator3.run()
    except Exception as e:
        logger.error(f"テスト3 失敗: {e}")
        results["RTCM注入設定"] = False
    
    # 結果サマリー
    logger.info("=" * 70)
    logger.info("【テスト結果サマリー】")
    logger.info("=" * 70)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"  {status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for p in results.values() if p)
    logger.info(f"\n総合: {passed}/{total} テスト合格")
    logger.info("=" * 70)
    
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
