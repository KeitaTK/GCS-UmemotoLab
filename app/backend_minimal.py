#!/usr/bin/env python3
"""
GCS Backend Server - Minimal Serial MAVLink Receiver for Raspberry Pi
No external dependencies (PyYAML, pymavlink extras) required.
"""

import sys
import time
import threading
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class SimpleSerialReader:
    """Read raw MAVLink data from serial port"""
    
    def __init__(self, port="/dev/ttyACM0", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.running = False
        self.data_buffer = bytearray()
        self.drone_info = {}
        
    def start(self):
        """Start reading from serial port"""
        self.running = True
        thread = threading.Thread(target=self._read_loop, daemon=True)
        thread.start()
        logger.info(f"Serial reader started: {self.port} @ {self.baudrate} baud")
        
    def stop(self):
        """Stop reading"""
        self.running = False
        
    def _read_loop(self):
        """Main read loop"""
        import serial
        
        ser = None
        while self.running:
            try:
                if ser is None or not ser.is_open:
                    ser = serial.Serial(self.port, self.baudrate, timeout=1)
                    logger.info(f"Serial port opened: {ser.port}")
                
                if ser.in_waiting > 0:
                    chunk = ser.read(ser.in_waiting)
                    self.data_buffer.extend(chunk)
                    self._process_buffer()
                    
            except ImportError:
                logger.error("pyserial not installed. Cannot read from serial port.")
                logger.info("Waiting for data on port instead...")
                break
            except Exception as e:
                logger.warning(f"Serial error: {e}")
                if ser:
                    try:
                        ser.close()
                    except:
                        pass
                ser = None
                time.sleep(1)
    
    def _process_buffer(self):
        """Parse MAVLink frames from buffer (simplified)"""
        # MAVLink v2 frames start with 0xFD
        while True:
            # Find next frame start
            try:
                idx = self.data_buffer.index(0xfd)
            except ValueError:
                # No complete frame, clear partial data
                if len(self.data_buffer) > 100:
                    self.data_buffer = self.data_buffer[-10:]
                break
            
            # Skip incomplete frames
            if idx > 0:
                self.data_buffer = self.data_buffer[idx:]
            
            # Need at least header (10 bytes) + 1 for checksum
            if len(self.data_buffer) < 11:
                break
            
            # Parse header
            payload_len = self.data_buffer[1]
            frame_len = 10 + payload_len + 2  # header + payload + checksum
            
            if len(self.data_buffer) < frame_len:
                break
            
            frame = self.data_buffer[:frame_len]
            self.data_buffer = self.data_buffer[frame_len:]
            
            self._parse_frame(frame)
    
    def _parse_frame(self, frame):
        """Parse a single MAVLink v2 frame (simplified)"""
        if len(frame) < 10:
            return
            
        # MAVLink v2 header format
        payload_len = frame[1]
        incompat_flags = frame[2]
        compat_flags = frame[3]
        seq = frame[4]
        sysid = frame[5]
        compid = frame[6]
        msgid = frame[7] | (frame[8] << 8) | (frame[9] << 16)
        
        # Track drones
        if sysid not in self.drone_info:
            self.drone_info[sysid] = {
                'first_seen': datetime.now(),
                'last_seen': datetime.now(),
                'message_count': 0
            }
        
        self.drone_info[sysid]['last_seen'] = datetime.now()
        self.drone_info[sysid]['message_count'] += 1
        
        # Log heartbeats (msgid 0)
        if msgid == 0:
            if payload_len >= 7:
                vehicle_type = frame[10]
                autopilot = frame[11]
                base_mode = frame[12]
                custom_mode = frame[13] | (frame[14] << 8) | (frame[15] << 16) | (frame[16] << 24)
                system_status = frame[17]
                
                armed = (base_mode & 0x80) != 0
                logger.info(f"HEARTBEAT from Drone {sysid}: type={vehicle_type}, armed={armed}, status={system_status}")
                
                self.drone_info[sysid]['heartbeat'] = {
                    'type': vehicle_type,
                    'autopilot': autopilot,
                    'armed': armed
                }
    
    def get_status(self):
        """Get current status"""
        if not self.drone_info:
            return "No drones detected yet"
        
        status = []
        for sysid, info in self.drone_info.items():
            elapsed = (datetime.now() - info['last_seen']).total_seconds()
            status.append(f"Drone {sysid}: {info['message_count']} msgs, last {elapsed:.1f}s ago")
        return "; ".join(status)

def main():
    """Main entry point"""
    logger.info("GCS Backend Server starting (Minimal MAVLink Serial Receiver)...")
    
    reader = SimpleSerialReader(port="/dev/ttyACM0", baudrate=115200)
    reader.start()
    
    try:
        last_status_time = time.time()
        while True:
            time.sleep(1)
            
            # Log status every 10 seconds
            current_time = time.time()
            if current_time - last_status_time >= 10:
                logger.info(f"Status: {reader.get_status()}")
                last_status_time = current_time
                
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        reader.stop()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
