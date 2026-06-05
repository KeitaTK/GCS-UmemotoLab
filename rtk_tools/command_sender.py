#!/usr/bin/env python3
"""
GCS Command Sender - Send MAVLink commands to Pixhawk
"""

import sys
import time
import struct
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class MAVLinkCommandSender:
    """Send MAVLink commands via serial port"""
    
    def __init__(self, port="/dev/ttyACM0", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        
    def connect(self):
        """Connect to serial port"""
        try:
            import serial
            self.ser = serial.Serial(self.port, self.baudrate, timeout=2)
            logger.info(f"Connected to {self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from serial port"""
        if self.ser:
            self.ser.close()
    
    def send_command_long(self, target_sysid, target_compid, command, param1=0, param2=0, 
                         param3=0, param4=0, param5=0, param6=0, param7=0):
        """
        Send COMMAND_LONG (msgid=76) to drone
        
        MAVLink v2 format:
        - Header: FD + len + incompat + compat + seq + sysid + compid
        - Message ID: 76 (COMMAND_LONG) [3 bytes LE]
        - Payload: param1-7 (28 bytes) + target_sysid (1) + target_compid (1) + command (2 LE) + confirmation (1)
        - Checksum: 2 bytes
        """
        
        if not self.ser:
            logger.error("Not connected")
            return False
        
        import struct
        
        # Build payload (32 bytes)
        payload = struct.pack('<fffff', param1, param2, param3, param4, param5)
        payload += struct.pack('<ffBBHB', param6, param7, target_sysid, target_compid, command, 0)
        
        # Build MAVLink v2 frame
        msgid = 76
        seq = 0
        my_sysid = 255  # GCS system ID
        my_compid = 0   # GCS component ID
        
        # Header
        frame = bytearray()
        frame.append(0xfd)  # MAVLink v2 start
        frame.append(len(payload))  # Payload length
        frame.append(0)  # Incompat flags
        frame.append(0)  # Compat flags
        frame.append(seq)  # Sequence number
        frame.append(my_sysid)  # Source system ID
        frame.append(my_compid)  # Source component ID
        
        # Message ID (24-bit little endian)
        frame.append(msgid & 0xFF)
        frame.append((msgid >> 8) & 0xFF)
        frame.append((msgid >> 16) & 0xFF)
        
        # Payload
        frame.extend(payload)
        
        # Calculate checksum (CRC-16 CCITT)
        crc = self._crc16(bytes(frame[1:]))
        frame.append(crc & 0xFF)
        frame.append((crc >> 8) & 0xFF)
        
        try:
            self.ser.write(frame)
            logger.info(f"Sent COMMAND_LONG: cmd={command} to system {target_sysid}")
            return True
        except Exception as e:
            logger.error(f"Failed to send command: {e}")
            return False
    
    def _crc16(self, data):
        """CRC-16 CCITT calculation"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc = crc >> 1
        return crc

def main():
    """Main entry point"""
    logger.info("GCS Command Sender - Testing ARM/DISARM")
    
    sender = MAVLinkCommandSender("/dev/ttyACM0", 115200)
    
    if not sender.connect():
        sys.exit(1)
    
    try:
        # Test 1: Send DISARM command (cmd=400)
        logger.info("Test 1: Sending DISARM command...")
        sender.send_command_long(target_sysid=1, target_compid=1, command=400)
        time.sleep(2)
        
        # Test 2: Send ARM command (cmd=400 with param1=1)
        logger.info("Test 2: Sending ARM command...")
        sender.send_command_long(target_sysid=1, target_compid=1, command=400, param1=1)
        time.sleep(2)
        
        # Test 3: Send DISARM again
        logger.info("Test 3: Sending DISARM command again...")
        sender.send_command_long(target_sysid=1, target_compid=1, command=400, param1=0)
        time.sleep(2)
        
        logger.info("Command tests completed")
        
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        sender.disconnect()

if __name__ == "__main__":
    main()
