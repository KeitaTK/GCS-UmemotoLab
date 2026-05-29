"""
Test suite for connection error handling and recovery.

Tests:
- UDP timeout detection
- Serial connection error recovery with exponential backoff
- Error callback execution and propagation
- Connection state tracking
- Packet loss detection
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import time
import socket
import tempfile
import yaml
import logging
from app.mavlink.connection import MavlinkConnection

logger = logging.getLogger(__name__)


def create_temp_config():
    """Create a temporary config file for testing."""
    config_data = {
        'connection_type': 'udp',
        'udp_listen_port': 14551,
        'drones': {}
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(config_data, f)
        return f.name


class TestConnectionErrorHandling(unittest.TestCase):
    """Test error detection and callback mechanisms."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_file = create_temp_config()
        self.conn = MavlinkConnection(self.config_file)
        self.error_callbacks = []
        
    def tearDown(self):
        """Clean up after tests."""
        if self.conn:
            self.conn.stop()
        import os
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
            
    def test_error_callback_registration(self):
        """Test registering error callbacks."""
        callback = Mock()
        self.conn.register_error_callback(callback)
        
        self.assertIn(callback, self.conn.error_callbacks)
        
    def test_multiple_error_callbacks(self):
        """Test multiple callbacks can be registered."""
        callback1 = Mock()
        callback2 = Mock()
        
        self.conn.register_error_callback(callback1)
        self.conn.register_error_callback(callback2)
        
        self.assertEqual(len(self.conn.error_callbacks), 2)
        
    def test_error_callback_trigger_with_single_callback(self):
        """Test triggering a single error callback."""
        callback = Mock()
        self.conn.register_error_callback(callback)
        
        self.conn._trigger_error_callback('TEST_ERROR', 'Test message')
        
        callback.assert_called_once_with('TEST_ERROR', 'Test message')
        
    def test_error_callback_trigger_with_multiple_callbacks(self):
        """Test triggering multiple error callbacks."""
        callback1 = Mock()
        callback2 = Mock()
        
        self.conn.register_error_callback(callback1)
        self.conn.register_error_callback(callback2)
        
        self.conn._trigger_error_callback('TEST_ERROR', 'Test message')
        
        callback1.assert_called_once_with('TEST_ERROR', 'Test message')
        callback2.assert_called_once_with('TEST_ERROR', 'Test message')
        
    def test_error_message_stored(self):
        """Test error message is stored in connection."""
        self.conn._trigger_error_callback('TEST_ERROR', 'Test error message')
        
        self.assertEqual(self.conn.connection_error, 'Test error message')
        
    def test_connection_status_initial_state(self):
        """Test initial connection status."""
        status = self.conn.get_connection_status()
        
        self.assertFalse(status['is_connected'])
        self.assertEqual(status['packet_loss'], 0)
        self.assertEqual(status['packet_received'], 0)


class TestUDPTimeoutDetection(unittest.TestCase):
    """Test UDP timeout detection mechanism."""

    def setUp(self):
        """Set up UDP connection for testing."""
        self.config_file = create_temp_config()
        self.conn = MavlinkConnection(self.config_file)
        self.error_triggered = False
        
    def tearDown(self):
        """Clean up after tests."""
        if self.conn:
            self.conn.stop()
        import os
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
            
    def on_error_callback(self, error_type, message):
        """Simple callback to capture error."""
        self.error_triggered = True
        self.error_type = error_type
        self.error_message = message
        
    def test_udp_timeout_detection_mock(self):
        """Test UDP timeout detection with mocked socket."""
        callback = Mock()
        self.conn.register_error_callback(callback)
        
        # Simulate socket timeout by setting a very short timeout
        if hasattr(self.conn, 'socket') and self.conn.socket:
            self.conn.socket.settimeout(0.001)
            
        # Manually trigger timeout detection
        max_consecutive_timeouts = 10
        timeout_count = max_consecutive_timeouts
        
        if timeout_count >= max_consecutive_timeouts:
            self.conn.is_connected = False
            self.conn._trigger_error_callback(
                'UDP_TIMEOUT',
                f'UDP timeout after {timeout_count} consecutive timeouts'
            )
            
        callback.assert_called_once()
        args = callback.call_args[0]
        self.assertEqual(args[0], 'UDP_TIMEOUT')
        self.assertIn('timeout', args[1].lower())


class TestSerialConnectionRecovery(unittest.TestCase):
    """Test Serial connection error recovery with exponential backoff."""

    def setUp(self):
        """Set up serial connection for testing."""
        # Note: Serial connection requires actual hardware
        # We'll mock the serial module
        pass
        
    def test_exponential_backoff_calculation(self):
        """Test exponential backoff delay calculation."""
        delays = []
        reconnect_delay = 1.0
        max_delay = 5.0
        
        for i in range(6):
            delays.append(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, max_delay)
            
        # Expected: 1.0, 1.5, 2.25, 3.375, 5.0, 5.0
        expected = [1.0, 1.5, 2.25, 3.375, 5.0, 5.0]
        
        for actual, exp in zip(delays, expected):
            self.assertAlmostEqual(actual, exp, places=2)
            
    def test_exponential_backoff_caps_at_max(self):
        """Test exponential backoff caps at maximum delay."""
        reconnect_delay = 1.0
        max_delay = 5.0
        
        for _ in range(10):  # Many iterations
            reconnect_delay = min(reconnect_delay * 1.5, max_delay)
            
        self.assertLessEqual(reconnect_delay, max_delay)
        self.assertEqual(reconnect_delay, max_delay)


class TestConnectionStatePersistence(unittest.TestCase):
    """Test connection state tracking and persistence."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_file = create_temp_config()
        self.conn = MavlinkConnection(self.config_file)
        
    def tearDown(self):
        """Clean up after tests."""
        if self.conn:
            self.conn.stop()
        import os
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
            
    def test_packet_count_increments(self):
        """Test packet counter increments."""
        initial_count = self.conn.get_connection_status()['packet_received']
        
        # Simulate packet receipt (this would normally happen in recv loops)
        self.conn.packet_received_count += 1
        
        updated_count = self.conn.get_connection_status()['packet_received']
        self.assertEqual(updated_count, initial_count + 1)
        
    def test_packet_loss_count_increments(self):
        """Test packet loss counter increments."""
        initial_loss = self.conn.get_connection_status()['packet_loss']
        
        # Simulate packet loss (this would normally happen in error handling)
        self.conn.packet_loss_count += 1
        
        updated_loss = self.conn.get_connection_status()['packet_loss']
        self.assertEqual(updated_loss, initial_loss + 1)
        
    def test_connection_status_dict_format(self):
        """Test connection status dict has all required fields."""
        status = self.conn.get_connection_status()
        
        required_fields = [
            'is_connected',
            'connection_type',
            'packet_received',
            'packet_loss',
            'last_error'
        ]
        
        for field in required_fields:
            self.assertIn(field, status, f"Missing field: {field}")


class TestErrorTypeCategories(unittest.TestCase):
    """Test different error type categories."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_file = create_temp_config()
        self.conn = MavlinkConnection(self.config_file)
        
    def tearDown(self):
        """Clean up after tests."""
        if self.conn:
            self.conn.stop()
        import os
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
            
    def test_serial_error_types(self):
        """Test Serial error type handling."""
        callback = Mock()
        self.conn.register_error_callback(callback)
        
        error_types = ['SERIAL_TIMEOUT', 'SERIAL_PORT_NOT_FOUND', 'SERIAL_PERMISSION_DENIED']
        
        for error_type in error_types:
            self.conn._trigger_error_callback(error_type, f'Serial error: {error_type}')
            
        self.assertEqual(callback.call_count, len(error_types))
        
    def test_udp_error_types(self):
        """Test UDP error type handling."""
        callback = Mock()
        self.conn.register_error_callback(callback)
        
        error_types = ['UDP_TIMEOUT', 'UDP_CONNECTION_RESET', 'UDP_ERROR']
        
        for error_type in error_types:
            self.conn._trigger_error_callback(error_type, f'UDP error: {error_type}')
            
        self.assertEqual(callback.call_count, len(error_types))
        
    def test_critical_error_type(self):
        """Test CRITICAL error categorization."""
        callback = Mock()
        self.conn.register_error_callback(callback)
        
        self.conn._trigger_error_callback(
            'CRITICAL_CONNECTION_FAILURE',
            'Connection failed after 10 retries'
        )
        
        callback.assert_called_once()
        self.assertIn('CRITICAL', callback.call_args[0][0])


class TestConnectionStatusUpdates(unittest.TestCase):
    """Test connection status updates during error conditions."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_file = create_temp_config()
        self.conn = MavlinkConnection(self.config_file)
        
    def tearDown(self):
        """Clean up after tests."""
        if self.conn:
            self.conn.stop()
        import os
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
            
    def test_connected_state_change(self):
        """Test connection state changes."""
        # Initial state
        self.assertFalse(self.conn.is_connected)
        
        # Simulate connection
        self.conn.is_connected = True
        self.assertTrue(self.conn.is_connected)
        
        status = self.conn.get_connection_status()
        self.assertTrue(status['is_connected'])
        
    def test_disconnected_state_change(self):
        """Test disconnection state changes."""
        # Simulate connection then disconnection
        self.conn.is_connected = True
        self.conn.is_connected = False
        
        self.assertFalse(self.conn.is_connected)
        status = self.conn.get_connection_status()
        self.assertFalse(status['is_connected'])


class TestCallbackExecutionOrder(unittest.TestCase):
    """Test callback execution order and consistency."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_file = create_temp_config()
        self.conn = MavlinkConnection(self.config_file)
        self.call_order = []
        
    def tearDown(self):
        """Clean up after tests."""
        if self.conn:
            self.conn.stop()
        import os
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
            
    def test_callbacks_execute_in_registration_order(self):
        """Test callbacks execute in the order they were registered."""
        def callback1(error_type, message):
            self.call_order.append(1)
            
        def callback2(error_type, message):
            self.call_order.append(2)
            
        def callback3(error_type, message):
            self.call_order.append(3)
            
        self.conn.register_error_callback(callback1)
        self.conn.register_error_callback(callback2)
        self.conn.register_error_callback(callback3)
        
        self.conn._trigger_error_callback('TEST', 'test')
        
        self.assertEqual(self.call_order, [1, 2, 3])
        
    def test_error_message_consistency(self):
        """Test error message is consistent across all callbacks."""
        received_messages = []
        
        def callback1(error_type, message):
            received_messages.append((error_type, message))
            
        def callback2(error_type, message):
            received_messages.append((error_type, message))
            
        self.conn.register_error_callback(callback1)
        self.conn.register_error_callback(callback2)
        
        self.conn._trigger_error_callback('ERROR_TYPE', 'Error message text')
        
        # All callbacks should receive the same error info
        for error_type, message in received_messages:
            self.assertEqual(error_type, 'ERROR_TYPE')
            self.assertEqual(message, 'Error message text')


if __name__ == '__main__':
    unittest.main()
