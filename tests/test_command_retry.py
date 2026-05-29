"""
Unit tests for command timeout and retry mechanisms in CommandDispatcher
"""
import unittest
import time
import sys
import os
from pathlib import Path

# Add app directory to path
app_dir = os.path.join(os.path.dirname(__file__), '..', 'app')
sys.path.insert(0, app_dir)

from mavlink.command_dispatcher import CommandDispatcher
from unittest.mock import Mock, MagicMock, patch


class TestCommandRetry(unittest.TestCase):
    """Test suite for command timeout and retry functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_connection = Mock()
        self.dispatcher = CommandDispatcher(self.mock_connection)
    
    def test_track_command_creates_pending_entry(self):
        """Test that _track_command creates a pending command entry"""
        system_id = 1
        command_id = 400  # ARM
        description = "ARM"
        
        self.dispatcher._track_command(system_id, command_id, description)
        
        pending = self.dispatcher.get_pending_commands(system_id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['command_id'], command_id)
        self.assertEqual(pending[0]['status'], 'pending')
        self.assertEqual(pending[0]['retries'], 0)
    
    def test_handle_command_ack_accepted(self):
        """Test handling COMMAND_ACK with result=0 (ACCEPTED)"""
        system_id = 1
        command_id = 400
        
        self.dispatcher._track_command(system_id, command_id, "ARM")
        self.dispatcher.handle_command_ack(system_id, command_id, result=0)
        
        pending = self.dispatcher.get_pending_commands(system_id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['status'], 'acked')
    
    def test_handle_command_ack_denied(self):
        """Test handling COMMAND_ACK with result=2 (DENIED)"""
        system_id = 1
        command_id = 400
        
        self.dispatcher._track_command(system_id, command_id, "ARM")
        self.dispatcher.handle_command_ack(system_id, command_id, result=2)
        
        pending = self.dispatcher.get_pending_commands(system_id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['status'], 'failed')
    
    def test_check_timeouts_triggers_retry(self):
        """Test that check_timeouts triggers retry when timeout occurs"""
        system_id = 1
        command_id = 400
        
        self.dispatcher._track_command(system_id, command_id, "ARM")
        
        # Artificially set sent_time to past to trigger timeout
        with self.dispatcher._pending_lock:
            for cmd in self.dispatcher._pending_commands.values():
                cmd['sent_time'] = time.time() - 10  # 10 seconds ago
        
        # Mock the resend method
        with patch.object(self.dispatcher, '_resend_command'):
            self.dispatcher.check_timeouts()
        
        pending = self.dispatcher.get_pending_commands(system_id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['retries'], 1)
    
    def test_check_timeouts_marks_failed_after_max_retries(self):
        """Test that command is marked as timeout after max retries exceeded"""
        system_id = 1
        command_id = 400
        
        self.dispatcher._track_command(system_id, command_id, "ARM")
        
        # Set retries to max_retries and trigger timeout
        with self.dispatcher._pending_lock:
            for cmd in self.dispatcher._pending_commands.values():
                cmd['retries'] = self.dispatcher.max_retries
                cmd['sent_time'] = time.time() - 10
        
        # Capture timeout callback
        timeout_called = []
        def on_timeout(system_id, command_id, description):
            timeout_called.append((system_id, command_id, description))
        
        self.dispatcher.register_timeout_callback(on_timeout)
        self.dispatcher.check_timeouts()
        
        # Check that timeout callback was called
        self.assertEqual(len(timeout_called), 1)
        self.assertEqual(timeout_called[0][0], system_id)
        self.assertEqual(timeout_called[0][1], command_id)
        
        # Check that command was removed from pending
        pending = self.dispatcher.get_pending_commands(system_id)
        self.assertEqual(len(pending), 0)
    
    def test_ack_callback_registration(self):
        """Test that ACK callbacks are properly registered and called"""
        system_id = 1
        command_id = 400
        
        ack_called = []
        def on_ack(sys_id, cmd_id, result, status_str):
            ack_called.append((sys_id, cmd_id, result, status_str))
        
        self.dispatcher.register_ack_callback(on_ack)
        self.dispatcher._track_command(system_id, command_id, "ARM")
        self.dispatcher.handle_command_ack(system_id, command_id, result=0)
        
        self.assertEqual(len(ack_called), 1)
        self.assertEqual(ack_called[0][0], system_id)
        self.assertEqual(ack_called[0][1], command_id)
        self.assertEqual(ack_called[0][2], 0)
        self.assertEqual(ack_called[0][3], "ACCEPTED")
    
    def test_get_ack_status_string(self):
        """Test MAV_RESULT code conversion to string"""
        test_cases = [
            (0, "ACCEPTED"),
            (1, "TEMPORARILY_REJECTED"),
            (2, "DENIED"),
            (3, "UNSUPPORTED"),
            (4, "FAILED"),
            (5, "CANCELLED"),
            (99, "UNKNOWN(99)"),
        ]
        
        for result_code, expected_str in test_cases:
            status_str = self.dispatcher._get_ack_status_string(result_code)
            self.assertEqual(status_str, expected_str)
    
    def test_multiple_pending_commands(self):
        """Test handling multiple pending commands simultaneously"""
        system_id = 1
        
        # Send multiple commands
        self.dispatcher._track_command(system_id, 400, "ARM")
        self.dispatcher._track_command(system_id, 22, "TAKEOFF")
        self.dispatcher._track_command(system_id, 21, "LAND")
        
        pending = self.dispatcher.get_pending_commands(system_id)
        self.assertEqual(len(pending), 3)
        
        # ACK the first command
        self.dispatcher.handle_command_ack(system_id, 400, result=0)
        
        pending = self.dispatcher.get_pending_commands(system_id)
        self.assertEqual(len(pending), 3)  # Still all 3, but one is acked
        
        acked_count = sum(1 for cmd in pending if cmd['status'] == 'acked')
        self.assertEqual(acked_count, 1)


if __name__ == '__main__':
    unittest.main()
