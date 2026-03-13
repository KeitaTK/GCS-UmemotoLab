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
                'message_count': 0,
                'message_types': {}
            }
        
        self.drone_info[sysid]['last_seen'] = datetime.now()
        self.drone_info[sysid]['message_count'] += 1
        
        # Track message types
        msg_type_name = self._get_message_name(msgid)
        if msg_type_name not in self.drone_info[sysid]['message_types']:
            self.drone_info[sysid]['message_types'][msg_type_name] = 0
        self.drone_info[sysid]['message_types'][msg_type_name] += 1
        
        # Parse specific messages
        if msgid == 0:  # HEARTBEAT
            self._parse_heartbeat(sysid, frame[10:])
        elif msgid == 1:  # SYS_STATUS
            self._parse_sys_status(sysid, frame[10:])
        elif msgid == 24:  # GPS_RAW_INT
            self._parse_gps_raw(sysid, frame[10:])
        elif msgid == 33:  # GLOBAL_POSITION_INT
            self._parse_global_position(sysid, frame[10:])
        elif msgid == 42:  # MISSION_CURRENT
            self._parse_mission_current(sysid, frame[10:])
        elif msgid == 76:  # COMMAND_LONG
            logger.debug(f"COMMAND_LONG from Drone {sysid}")
        elif msgid == 77:  # COMMAND_ACK
            self._parse_command_ack(sysid, frame[10:])
        elif msgid == 253:  # NAMED_VALUE_FLOAT
            self._parse_named_value_float(sysid, frame[10:])
    
    def _get_message_name(self, msgid):
        """Get message name from ID"""
        names = {
            0: 'HEARTBEAT', 1: 'SYS_STATUS', 24: 'GPS_RAW_INT', 
            33: 'GLOBAL_POSITION_INT', 42: 'MISSION_CURRENT', 
            76: 'COMMAND_LONG', 77: 'COMMAND_ACK', 253: 'NAMED_VALUE_FLOAT'
        }
        return names.get(msgid, f'MSG_{msgid}')
    
    def _parse_heartbeat(self, sysid, payload):
        """Parse HEARTBEAT (msgid=0)"""
        if len(payload) < 9:
            return
        
        vehicle_type = payload[0]
        autopilot = payload[1]
        base_mode = payload[2]
        custom_mode = payload[3] | (payload[4] << 8) | (payload[5] << 16) | (payload[6] << 24)
        system_status = payload[7]
        
        armed = (base_mode & 0x80) != 0
        logger.info(f"HEARTBEAT from Drone {sysid}: type={vehicle_type}, armed={armed}, status={system_status}")
        
        self.drone_info[sysid]['heartbeat'] = {
            'type': vehicle_type,
            'autopilot': autopilot,
            'armed': armed,
            'status': system_status
        }
    
    def _parse_sys_status(self, sysid, payload):
        """Parse SYS_STATUS (msgid=1)"""
        if len(payload) < 31:
            return
        
        onboard_control_sensors_health = payload[0] | (payload[1] << 8) | (payload[2] << 16) | (payload[3] << 24)
        battery_remaining = payload[24]
        
        if 'sys_status' not in self.drone_info[sysid]:
            self.drone_info[sysid]['sys_status'] = {}
        
        self.drone_info[sysid]['sys_status'] = {
            'battery_remaining': battery_remaining
        }
        logger.debug(f"SYS_STATUS from Drone {sysid}: battery={battery_remaining}%")
    
    def _parse_gps_raw(self, sysid, payload):
        """Parse GPS_RAW_INT (msgid=24)"""
        if len(payload) < 30:
            return
        
        fix_type = payload[24]
        lat = int.from_bytes(payload[4:8], 'little', signed=True)
        lon = int.from_bytes(payload[8:12], 'little', signed=True)
        
        logger.debug(f"GPS_RAW from Drone {sysid}: fix={fix_type}, lat={lat/1e7:.6f}, lon={lon/1e7:.6f}")
    
    def _parse_global_position(self, sysid, payload):
        """Parse GLOBAL_POSITION_INT (msgid=33)"""
        if len(payload) < 28:
            return
        
        lat = int.from_bytes(payload[0:4], 'little', signed=True)
        lon = int.from_bytes(payload[4:8], 'little', signed=True)
        alt = int.from_bytes(payload[8:12], 'little', signed=True)
        
        logger.debug(f"GLOBAL_POSITION from Drone {sysid}: lat={lat/1e7:.6f}, lon={lon/1e7:.6f}, alt={alt/1000:.2f}m")
    
    def _parse_mission_current(self, sysid, payload):
        """Parse MISSION_CURRENT (msgid=42)"""
        if len(payload) < 4:
            return
        
        seq = payload[0] | (payload[1] << 8)
        logger.debug(f"MISSION_CURRENT from Drone {sysid}: seq={seq}")
    
    def _parse_named_value_float(self, sysid, payload):
        """Parse NAMED_VALUE_FLOAT (msgid=253)"""
        if len(payload) < 12:
            return
        
        # Time boot ms (4 bytes) + value (4 bytes) + name (10 bytes)
        import struct
        time_boot = struct.unpack('<I', payload[0:4])[0]
        value = struct.unpack('<f', payload[4:8])[0]
        name = payload[8:18].decode('utf-8', errors='ignore').strip('\x00')
        
        logger.debug(f"NAMED_VALUE_FLOAT from Drone {sysid}: {name}={value:.3f}")
    
    def _parse_command_ack(self, sysid, payload):
        """Parse COMMAND_ACK (msgid=77)"""
        if len(payload) < 3:
            return
        
        command = payload[0] | (payload[1] << 8)
        result = payload[2]
        
        result_names = {
            0: 'ACCEPTED',
            1: 'REJECTED',
            2: 'FAILED',
            3: 'TEMPORARILY_REJECTED',
            4: 'UNSUPPORTED'
        }
        
        result_name = result_names.get(result, f'UNKNOWN_{result}')
        logger.info(f"COMMAND_ACK from Drone {sysid}: cmd={command}, result={result_name}")

    
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
