import pytest
from unittest.mock import MagicMock
from app.mavlink.command_dispatcher import CommandDispatcher

def test_command_dispatcher_arm():
    mock_conn = MagicMock()
    dispatcher = CommandDispatcher(mock_conn)
    
    dispatcher.arm(system_id=1, component_id=1)
    mock_conn.send_command_long.assert_called_once_with(1, 1, command=400, confirmation=0, param1=1)

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
