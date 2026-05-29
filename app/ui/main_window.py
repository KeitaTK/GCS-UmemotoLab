from PySide6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QWidget, QHBoxLayout, 
    QListWidget, QPushButton, QMessageBox, QGroupBox, QGridLayout,
    QTabWidget, QScrollArea
)
from PySide6.QtCore import QTimer
import logging
import time

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, telemetry_store, dispatcher=None, connection=None):
        super().__init__()
        self.telemetry_store = telemetry_store
        self.dispatcher = dispatcher
        self.connection = connection  # MavlinkConnection instance
        self.setWindowTitle("GCS Telemetry")
        self.resize(1200, 800)
        
        # Command ACK status tracking
        self.last_command_status = {}  # {(system_id, cmd_id): status_str}
        self.last_error_message = ""
        self._setup_dispatcher_callbacks()
        self._setup_connection_callbacks()  # Register connection error callbacks

        # --- UI構成 ---
        central = QWidget()
        main_layout = QHBoxLayout()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # ドローンリスト（左パネル）
        self.drone_list = QListWidget()
        self.drone_list.setMinimumWidth(200)
        self.drone_list.itemSelectionChanged.connect(self._on_drone_selected)
        main_layout.addWidget(self.drone_list)

        # タブビュー（右パネル）
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget, 1)

        # === Tab 1: Dashboard ===
        self.dashboard_widget = self._create_dashboard_tab()
        self.tab_widget.addTab(self.dashboard_widget, "Dashboard")

        # === Tab 2: Graph ===
        self.graph_widget = self._create_graph_tab()
        self.tab_widget.addTab(self.graph_widget, "Graph")

        # === Tab 3: Raw Data ===
        self.raw_data_widget = self._create_raw_data_tab()
        self.tab_widget.addTab(self.raw_data_widget, "Raw Data")

        self._setup_timer()

    def _create_dashboard_tab(self):
        """Create the Dashboard tab with telemetry displays"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        dashboard = QWidget()
        layout = QVBoxLayout()
        dashboard.setLayout(layout)

        # ===== Connection Status Group (NEW) =====
        conn_group = QGroupBox("Connection Status")
        conn_layout = QGridLayout()
        self.conn_status_label = QLabel("Status: Disconnected")
        self.conn_type_label = QLabel("Type: -")
        self.conn_packet_label = QLabel("Packets: 0")
        self.conn_error_label = QLabel("Error: None")
        conn_layout.addWidget(QLabel("Status:"), 0, 0)
        conn_layout.addWidget(self.conn_status_label, 0, 1)
        conn_layout.addWidget(QLabel("Type:"), 1, 0)
        conn_layout.addWidget(self.conn_type_label, 1, 1)
        conn_layout.addWidget(QLabel("Packets:"), 2, 0)
        conn_layout.addWidget(self.conn_packet_label, 2, 1)
        conn_layout.addWidget(QLabel("Last Error:"), 3, 0)
        conn_layout.addWidget(self.conn_error_label, 3, 1)
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)
        
        # ===== System Status Group =====
        status_group = QGroupBox("System Status")
        status_layout = QGridLayout()
        self.status_armed_label = QLabel("Armed: N/A")
        self.status_mode_label = QLabel("Mode: N/A")
        status_layout.addWidget(QLabel("Armed:"), 0, 0)
        status_layout.addWidget(self.status_armed_label, 0, 1)
        status_layout.addWidget(QLabel("Mode:"), 1, 0)
        status_layout.addWidget(self.status_mode_label, 1, 1)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # ===== Battery Status Group =====
        battery_group = QGroupBox("Battery Status")
        battery_layout = QGridLayout()
        self.battery_voltage_label = QLabel("Voltage: N/A")
        self.battery_current_label = QLabel("Current: N/A")
        self.battery_remaining_label = QLabel("Remaining: N/A")
        battery_layout.addWidget(QLabel("Voltage:"), 0, 0)
        battery_layout.addWidget(self.battery_voltage_label, 0, 1)
        battery_layout.addWidget(QLabel("Current:"), 1, 0)
        battery_layout.addWidget(self.battery_current_label, 1, 1)
        battery_layout.addWidget(QLabel("Remaining:"), 2, 0)
        battery_layout.addWidget(self.battery_remaining_label, 2, 1)
        battery_group.setLayout(battery_layout)
        layout.addWidget(battery_group)

        # ===== GPS Status Group =====
        gps_group = QGroupBox("GPS Status")
        gps_layout = QGridLayout()
        self.gps_satellites_label = QLabel("Satellites: 0")
        self.gps_coords_label = QLabel("Lat/Lon: N/A")
        self.gps_altitude_label = QLabel("Altitude: N/A")
        gps_layout.addWidget(QLabel("Satellites:"), 0, 0)
        gps_layout.addWidget(self.gps_satellites_label, 0, 1)
        gps_layout.addWidget(QLabel("Position:"), 1, 0)
        gps_layout.addWidget(self.gps_coords_label, 1, 1)
        gps_layout.addWidget(QLabel("Altitude:"), 2, 0)
        gps_layout.addWidget(self.gps_altitude_label, 2, 1)
        gps_group.setLayout(gps_layout)
        layout.addWidget(gps_group)

        # ===== Command Status Group =====
        cmd_status_group = QGroupBox("Command Status & Retry")
        cmd_status_layout = QGridLayout()
        self.cmd_status_label = QLabel("Last Command: -")
        self.cmd_ack_label = QLabel("ACK Status: Waiting...")
        self.cmd_pending_label = QLabel("Pending: 0")
        self.cmd_retry_label = QLabel("Retries: 0/3")
        cmd_status_layout.addWidget(QLabel("Last Command:"), 0, 0)
        cmd_status_layout.addWidget(self.cmd_status_label, 0, 1)
        cmd_status_layout.addWidget(QLabel("ACK:"), 1, 0)
        cmd_status_layout.addWidget(self.cmd_ack_label, 1, 1)
        cmd_status_layout.addWidget(QLabel("Pending:"), 2, 0)
        cmd_status_layout.addWidget(self.cmd_pending_label, 2, 1)
        cmd_status_layout.addWidget(QLabel("Retries:"), 3, 0)
        cmd_status_layout.addWidget(self.cmd_retry_label, 3, 1)
        cmd_status_group.setLayout(cmd_status_layout)
        layout.addWidget(cmd_status_group)

        # RTKステータス
        self.rtk_status_label = QLabel("RTK Status: Unknown")
        layout.addWidget(self.rtk_status_label)

        # 制御ボタン
        control_panel = QHBoxLayout()
        self.btn_arm = QPushButton("Arm")
        self.btn_disarm = QPushButton("Disarm")
        self.btn_takeoff = QPushButton("Takeoff (10m)")
        self.btn_land = QPushButton("Land")

        control_panel.addWidget(self.btn_arm)
        control_panel.addWidget(self.btn_disarm)
        control_panel.addWidget(self.btn_takeoff)
        control_panel.addWidget(self.btn_land)

        self.btn_arm.clicked.connect(self.cmd_arm)
        self.btn_disarm.clicked.connect(self.cmd_disarm)
        self.btn_takeoff.clicked.connect(self.cmd_takeoff)
        self.btn_land.clicked.connect(self.cmd_land)

        layout.addLayout(control_panel)
        layout.addStretch()

        scroll_area.setWidget(dashboard)
        return scroll_area

    def _create_graph_tab(self):
        """Create the Graph tab with real-time plotting"""
        from ui.telemetry_plotter import TelemetryPlotter
        
        self.plotter = TelemetryPlotter(self.telemetry_store)
        return self.plotter

    def _create_raw_data_tab(self):
        """Create the Raw Data tab"""
        layout = QVBoxLayout()
        
        self.raw_data_label = QLabel("Raw MAVLink Data (JSON-like format)")
        layout.addWidget(self.raw_data_label)
        
        self.raw_data_text = QLabel("")
        self.raw_data_text.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidget(self.raw_data_text)
        layout.addWidget(scroll)
        
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def get_selected_system_id(self):
        selected_items = self.drone_list.selectedItems()
        if not selected_items:
            return None
        sysid_str = selected_items[0].text()
        try:
            return int(sysid_str)
        except ValueError:
            return None

    def _on_drone_selected(self):
        """Called when drone selection changes"""
        self.update_label()

    def cmd_arm(self):
        sysid = self.get_selected_system_id()
        if not sysid:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        if self.dispatcher:
            logger.info(f"ARM command sent to drone {sysid}")
            self.dispatcher.arm(sysid, component_id=1)

    def cmd_disarm(self):
        sysid = self.get_selected_system_id()
        if not sysid:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        if self.dispatcher:
            logger.info(f"DISARM command sent to drone {sysid}")
            self.dispatcher.disarm(sysid, component_id=1)

    def cmd_takeoff(self):
        sysid = self.get_selected_system_id()
        if not sysid:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        if self.dispatcher:
            logger.info(f"TAKEOFF command sent to drone {sysid}")
            self.dispatcher.takeoff(sysid, component_id=1, altitude=10.0)

    def cmd_land(self):
        sysid = self.get_selected_system_id()
        if not sysid:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        if self.dispatcher:
            logger.info(f"LAND command sent to drone {sysid}")
            self.dispatcher.land(sysid, component_id=1)

    def _setup_dispatcher_callbacks(self):
        """Register callbacks for command ACK and timeout events."""
        if not self.dispatcher:
            return
        
        def on_ack(system_id, command_id, result, status_str):
            """Called when COMMAND_ACK is received."""
            self.last_command_status[(system_id, command_id)] = {
                'status': status_str,
                'time': time.time()
            }
            logger.info(f"COMMAND_ACK: system_id={system_id}, cmd={command_id}, result={status_str}")
            self._update_command_status_display()
        
        def on_timeout(system_id, command_id, description):
            """Called when command times out."""
            self.last_command_status[(system_id, command_id)] = {
                'status': 'TIMEOUT',
                'time': time.time()
            }
            logger.warning(f"Command TIMEOUT: system_id={system_id}, {description}")
            QMessageBox.warning(self, "Command Timeout", f"Command {description} timed out on drone {system_id}")
            self._update_command_status_display()
        
        self.dispatcher.register_ack_callback(on_ack)
        self.dispatcher.register_timeout_callback(on_timeout)

    def _setup_connection_callbacks(self):
        """Register callbacks for connection error events."""
        if not self.connection:
            return
        
        def on_connection_error(error_type: str, message: str):
            """Called when connection error occurs."""
            self.last_error_message = f"{error_type}: {message}"
            logger.warning(f"Connection error: {error_type} - {message}")
            
            # Show warning dialog for critical errors
            if 'CRITICAL' in error_type or 'TIMEOUT' in error_type:
                QMessageBox.warning(self, "Connection Error", 
                    f"{error_type}\n{message}", QMessageBox.Ok)
            
            self._update_connection_status_display()
        
        self.connection.register_error_callback(on_connection_error)

    def _update_connection_status_display(self):
        """Update connection status labels in the Connection Status Group."""
        if not self.connection:
            self.conn_status_label.setText("Status: Not initialized")
            return
        
        try:
            status = self.connection.get_connection_status()
            
            # Connection status
            is_connected = status.get('is_connected', False)
            status_text = "Connected" if is_connected else "Disconnected"
            self.conn_status_label.setText(f"Status: {status_text}")
            self.conn_status_label.setStyleSheet(
                "color: green;" if is_connected else "color: red; font-weight: bold;"
            )
            
            # Connection type
            conn_type = status.get('connection_type', 'Unknown')
            self.conn_type_label.setText(f"Type: {conn_type}")
            
            # Packet statistics
            packets_received = status.get('packet_received', 0)
            packets_lost = status.get('packet_loss', 0)
            self.conn_packet_label.setText(
                f"Packets: RX={packets_received} Loss={packets_lost}"
            )
            
            # Error information
            error_msg = self.last_error_message if hasattr(self, 'last_error_message') else "None"
            self.conn_error_label.setText(f"Error: {error_msg}")
            if error_msg != "None":
                self.conn_error_label.setStyleSheet("color: orange; font-weight: bold;")
            else:
                self.conn_error_label.setStyleSheet("color: green;")
                
        except Exception as e:
            logger.error(f"Error updating connection status display: {e}")
            self.conn_status_label.setText(f"Status: Error - {str(e)[:30]}")

    def _update_command_status_display(self):
        """Update command status labels in UI, including retry information."""
        sysid = self.get_selected_system_id()
        if not sysid:
            self.cmd_pending_label.setText("Pending: -")
            self.cmd_retry_label.setText("Retries: -")
            return
        
        # Get pending commands for this drone
        pending = self.dispatcher.get_pending_commands(sysid) if self.dispatcher else []
        self.cmd_pending_label.setText(f"Pending: {len(pending)}")
        
        # Get retry information from pending commands
        max_retries = 0
        current_retries = 0
        for cmd in pending:
            if cmd.get('status') == 'pending':
                current_retries = cmd.get('retries', 0)
                max_retries = self.dispatcher.max_retries if self.dispatcher else 3
        
        self.cmd_retry_label.setText(f"Retries: {current_retries}/{max_retries}")
        
        # Update retry label color based on retry count
        if current_retries == 0:
            self.cmd_retry_label.setStyleSheet("color: green;")
        elif current_retries < max_retries:
            self.cmd_retry_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.cmd_retry_label.setStyleSheet("color: red; font-weight: bold;")
        
        # Get last command status
        if self.last_command_status:
            last_key = list(self.last_command_status.keys())[-1]
            last_status = self.last_command_status[last_key]
            status_str = last_status.get('status', 'Unknown')
            self.cmd_ack_label.setText(f"ACK: {status_str}")
            # Color code: Green for ACCEPTED, Red for others
            if status_str == 'ACCEPTED':
                self.cmd_ack_label.setStyleSheet("color: green; font-weight: bold;")
            elif status_str in ['TIMEOUT', 'FAILED', 'DENIED']:
                self.cmd_ack_label.setStyleSheet("color: red; font-weight: bold;")
            else:
                self.cmd_ack_label.setStyleSheet("color: orange; font-weight: bold;")


    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_displays)
        self.timer.start(1000)  # Update every 1 second

    def update_displays(self):
        """Update all display elements"""
        self.update_dashboard()
        self.update_graph()
        self.update_raw_data()
        self._update_connection_status_display()

    def update_dashboard(self):
        """Update dashboard tab telemetry displays"""
        all_data = self.telemetry_store.get_all()
        drone_ids = []
        
        sysid = self.get_selected_system_id()
        
        for sysid_iter, messages in all_data.items():
            drone_ids.append(str(sysid_iter))
        
        # Update System Status if drone selected
        if sysid:
            hb = self.telemetry_store.get_heartbeat(sysid)
            if hb:
                try:
                    armed = (hb.base_mode & 0x80) != 0
                    self.status_armed_label.setText("🟢 ARMED" if armed else "🔴 DISARMED")
                    self.status_mode_label.setText(f"{getattr(hb, 'custom_mode', 'N/A')}")
                except Exception as e:
                    logger.debug(f"Error processing HEARTBEAT: {e}")
            
            # Update Battery Status
            sys_status = self.telemetry_store.get_sys_status(sysid)
            if sys_status:
                try:
                    voltage_mv = getattr(sys_status, 'voltage_battery', 0)
                    current_ma = getattr(sys_status, 'current_battery', 0)
                    remaining = getattr(sys_status, 'battery_remaining', -1)
                    
                    self.battery_voltage_label.setText(f"{voltage_mv/1000.0:.2f} V")
                    self.battery_current_label.setText(f"{current_ma/100.0:.2f} A")
                    self.battery_remaining_label.setText(f"{remaining}%" if remaining >= 0 else "N/A")
                except Exception as e:
                    logger.debug(f"Error processing SYS_STATUS: {e}")
            
            # Update GPS Status
            if sys_status:
                try:
                    gps_sats = getattr(sys_status, 'gps_nsat', 0)
                    self.gps_satellites_label.setText(f"{gps_sats} satellites")
                except Exception as e:
                    logger.debug(f"Error processing GPS sat count: {e}")
            
            global_pos = self.telemetry_store.get_global_position(sysid)
            if global_pos:
                try:
                    lat = getattr(global_pos, 'lat', 0) / 1e7
                    lon = getattr(global_pos, 'lon', 0) / 1e7
                    alt_msl = getattr(global_pos, 'alt', 0) / 1000.0
                    
                    self.gps_coords_label.setText(f"{lat:.6f}, {lon:.6f}")
                    self.gps_altitude_label.setText(f"{alt_msl:.1f} m")
                except Exception as e:
                    logger.debug(f"Error processing GLOBAL_POSITION_INT: {e}")
        
        # Update command status display
        self._update_command_status_display()
        
        # ドローンリストの更新
        existing_items = [self.drone_list.item(i).text() for i in range(self.drone_list.count())]
        for drone_id in drone_ids:
            if drone_id not in existing_items:
                self.drone_list.addItem(drone_id)

    def update_graph(self):
        """Update graph tab with latest telemetry data"""
        try:
            if hasattr(self, 'plotter'):
                self.plotter.update_data(self.telemetry_store)
        except Exception as e:
            logger.debug(f"Error updating plotter: {e}")

    def update_raw_data(self):
        """Update raw data tab"""
        try:
            sysid = self.get_selected_system_id()
            if not sysid:
                self.raw_data_text.setText("No drone selected")
                return
            
            all_data = self.telemetry_store.get_all()
            if sysid not in all_data:
                self.raw_data_text.setText(f"No data for drone {sysid}")
                return
            
            messages = all_data[sysid]
            raw_text = f"System ID: {sysid}\n\n"
            
            for msg_type, msg in list(messages.items())[:10]:  # Show first 10 messages
                raw_text += f"{msg_type}: {str(msg)[:100]}...\n"
            
            self.raw_data_text.setText(raw_text)
        except Exception as e:
            logger.debug(f"Error updating raw data: {e}")

    def update_rtk_status(self, status):
        """Update RTK status indicator"""
        self.rtk_status_label.setText(f"RTK Status: {status}")
