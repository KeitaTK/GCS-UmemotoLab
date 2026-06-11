import sys
from pathlib import Path

# app/ ディレクトリを sys.path に追加（mavlink.* 等のインポートに必要）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))

import pytest
from unittest.mock import MagicMock, patch
from mavlink.connection import MavlinkConnection
from rtk_tools.command_dispatcher import CommandDispatcher

def test_command_dispatcher_arm():
    mock_conn = MagicMock()
    dispatcher = CommandDispatcher(mock_conn)
    
    # threading.Timer をモックして即時実行させる
    with patch('threading.Timer') as mock_timer:
        dispatcher.arm(system_id=1, component_id=1)
        
        # 1つ目のコール: モードセット(176)
        mock_conn.send_command_long.assert_any_call(1, 1, command=176, confirmation=0, param1=0)
        
        # Timerが作成され、0.3秒遅延 + コールバックが渡されていることを確認
        assert mock_timer.call_count == 1
        timer_args, _ = mock_timer.call_args
        assert timer_args[0] == 0.3  # delay
        assert callable(timer_args[1])  # callback function
        
        # コールバックを手動実行して2つ目のコマンドを検証
        callback = timer_args[1]
        callback()
        mock_conn.send_command_long.assert_any_call(1, 1, command=400, confirmation=1, param1=1)

def test_command_dispatcher_disarm():
    mock_conn = MagicMock()
    dispatcher = CommandDispatcher(mock_conn)
    
    dispatcher.disarm(system_id=2, component_id=1)
    mock_conn.send_command_long.assert_called_once_with(2, 1, command=400, confirmation=0, param1=0)

def test_command_dispatcher_takeoff():
    mock_conn = MagicMock()
    dispatcher = CommandDispatcher(mock_conn)
    
    dispatcher.takeoff(system_id=1, component_id=1, altitude=15.5)
    mock_conn.send_command_long.assert_called_once_with(1, 1, command=22, confirmation=0, param7=15.5)
