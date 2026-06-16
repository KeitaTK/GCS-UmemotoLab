from PySide6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QWidget, QHBoxLayout, 
    QListWidget, QPushButton, QMessageBox, QGroupBox, QGridLayout,
    QTabWidget, QScrollArea, QDoubleSpinBox, QAbstractItemView, QCheckBox
)
from PySide6.QtCore import QTimer, Signal, QObject
import logging
import time

logger = logging.getLogger(__name__)

# Thread-safe signal emitter for GUI updates
class GuiSignals(QObject):
    """Signals for thread-safe GUI updates"""
    show_warning = Signal(str, str)  # title, message
    show_error = Signal(str, str)    # title, message
    update_connection_status = Signal()
    update_command_status = Signal()

class MainWindow(QMainWindow):
    def __init__(self, telemetry_store, dispatcher=None, connection=None, rtcm_reader=None):
        super().__init__()
        
        # Initialize GUI signals for thread-safe updates
        self.gui_signals = GuiSignals()
        self.gui_signals.show_warning.connect(self._show_warning_dialog)
        self.gui_signals.show_error.connect(self._show_error_dialog)
        self.gui_signals.update_connection_status.connect(self._update_connection_status_display)
        self.gui_signals.update_command_status.connect(self._update_command_status_display)
        
        self.telemetry_store = telemetry_store
        self.dispatcher = dispatcher
        self.connection = connection  # MavlinkConnection instance
        self.rtcm_reader = rtcm_reader
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
        self.drone_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.drone_list.itemSelectionChanged.connect(self._on_drone_selected)
        main_layout.addWidget(self.drone_list)

        # タブビュー（右パネル）
        self.tab_widget = QTabWidget()
        self.tab_widget.setMovable(True)
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
        self.gps_fix_label = QLabel("Fix: N/A")
        self.gps_satellites_label = QLabel("Satellites: 0")
        self.gps_coords_label = QLabel("Lat/Lon: N/A")
        self.gps_altitude_label = QLabel("Altitude: N/A")
        self.gps_hdop_label = QLabel("HDOP: N/A")
        gps_layout.addWidget(QLabel("Fix:"), 0, 0)
        gps_layout.addWidget(self.gps_fix_label, 0, 1)
        gps_layout.addWidget(QLabel("Satellites:"), 1, 0)
        gps_layout.addWidget(self.gps_satellites_label, 1, 1)
        gps_layout.addWidget(QLabel("Position:"), 2, 0)
        gps_layout.addWidget(self.gps_coords_label, 2, 1)
        gps_layout.addWidget(QLabel("Altitude:"), 3, 0)
        gps_layout.addWidget(self.gps_altitude_label, 3, 1)
        gps_layout.addWidget(QLabel("HDOP:"), 4, 0)
        gps_layout.addWidget(self.gps_hdop_label, 4, 1)
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

        # ===== Flight Control Group =====
        flight_group = QGroupBox("Flight Control")
        flight_layout = QGridLayout()

        self.takeoff_altitude_spin = QDoubleSpinBox()
        self.takeoff_altitude_spin.setRange(1.0, 500.0)
        self.takeoff_altitude_spin.setValue(10.0)
        self.takeoff_altitude_spin.setSuffix(" m")

        self.land_descent_rate_spin = QDoubleSpinBox()
        self.land_descent_rate_spin.setRange(0.0, 20.0)
        self.land_descent_rate_spin.setValue(1.5)
        self.land_descent_rate_spin.setSingleStep(0.5)
        self.land_descent_rate_spin.setSuffix(" m/s")

        self.guided_north_spin = QDoubleSpinBox()
        self.guided_north_spin.setRange(-500.0, 500.0)
        self.guided_north_spin.setValue(0.0)
        self.guided_east_spin = QDoubleSpinBox()
        self.guided_east_spin.setRange(-500.0, 500.0)
        self.guided_east_spin.setValue(0.0)
        self.guided_down_spin = QDoubleSpinBox()
        self.guided_down_spin.setRange(-500.0, 500.0)
        self.guided_down_spin.setValue(0.0)

        self.guided_vx_spin = QDoubleSpinBox()
        self.guided_vx_spin.setRange(-20.0, 20.0)
        self.guided_vy_spin = QDoubleSpinBox()
        self.guided_vy_spin.setRange(-20.0, 20.0)
        self.guided_vz_spin = QDoubleSpinBox()
        self.guided_vz_spin.setRange(-20.0, 20.0)
        self.guided_yaw_spin = QDoubleSpinBox()
        self.guided_yaw_spin.setRange(-180.0, 180.0)
        self.guided_yaw_spin.setSuffix(" deg")

        self.btn_takeoff = QPushButton("Takeoff")
        self.btn_land = QPushButton("Land")
        self.btn_guided_position = QPushButton("Send Guided Position")
        self.btn_guided_velocity = QPushButton("Send Guided Velocity")

        flight_layout.addWidget(QLabel("Takeoff Altitude:"), 0, 0)
        flight_layout.addWidget(self.takeoff_altitude_spin, 0, 1)
        flight_layout.addWidget(QLabel("Land Descent Rate:"), 1, 0)
        flight_layout.addWidget(self.land_descent_rate_spin, 1, 1)
        flight_layout.addWidget(self.btn_takeoff, 0, 2)
        flight_layout.addWidget(self.btn_land, 1, 2)

        flight_layout.addWidget(QLabel("North:"), 2, 0)
        flight_layout.addWidget(self.guided_north_spin, 2, 1)
        flight_layout.addWidget(QLabel("East:"), 3, 0)
        flight_layout.addWidget(self.guided_east_spin, 3, 1)
        flight_layout.addWidget(QLabel("Down:"), 4, 0)
        flight_layout.addWidget(self.guided_down_spin, 4, 1)

        flight_layout.addWidget(QLabel("Vx:"), 2, 2)
        flight_layout.addWidget(self.guided_vx_spin, 2, 3)
        flight_layout.addWidget(QLabel("Vy:"), 3, 2)
        flight_layout.addWidget(self.guided_vy_spin, 3, 3)
        flight_layout.addWidget(QLabel("Vz:"), 4, 2)
        flight_layout.addWidget(self.guided_vz_spin, 4, 3)
        flight_layout.addWidget(QLabel("Yaw:"), 5, 2)
        flight_layout.addWidget(self.guided_yaw_spin, 5, 3)

        flight_layout.addWidget(self.btn_guided_position, 5, 0, 1, 2)
        flight_layout.addWidget(self.btn_guided_velocity, 6, 0, 1, 2)

        # Indoor flight buttons (STABILIZE mode, no GPS)
        self.btn_indoor_takeoff = QPushButton("↑ 屋内離陸")
        self.btn_indoor_takeoff.setToolTip("STABILIZEモードでスロットル65%上昇")
        self.btn_indoor_land = QPushButton("↓ 屋内着陸")
        self.btn_indoor_land.setToolTip("STABILIZEモードでスロットル最小→降下")
        flight_layout.addWidget(QLabel("屋内:"), 7, 0)
        flight_layout.addWidget(self.btn_indoor_takeoff, 7, 1)
        flight_layout.addWidget(self.btn_indoor_land, 7, 2)

        self.btn_indoor_auto = QPushButton("▶ 自動テスト(離陸→1m→5秒→着陸)")
        self.btn_indoor_auto.setToolTip("自動: 65%→1.5秒上昇→50%で5秒ホバリング→着陸")
        flight_layout.addWidget(self.btn_indoor_auto, 8, 0, 1, 3)

        flight_group.setLayout(flight_layout)
        layout.addWidget(flight_group)

        # 制御ボタン
        control_panel = QHBoxLayout()
        self.btn_arm = QPushButton("Arm")
        self.btn_disarm = QPushButton("Disarm")
        self.chk_indoor_mode = QCheckBox("屋内モード(GPS不要)")
        self.chk_indoor_mode.setToolTip(
            "屋内テスト用。以下を実行してからアーム:\n"
            "• ARMING_CHECK=0, AHRS_EKF_TYPE=0\n"
            "• STABILIZEモード (GPS/EKF/高度不要)"
        )
        self.btn_restore_params = QPushButton("パラメータ復元")
        self.btn_restore_params.setToolTip(
            "ARMING_CHECK=1, AHRS_EKF_TYPE=3 に戻す\n"
            "屋外フライト前に必ず実行してください"
        )
        self.btn_select_all = QPushButton("Select All")
        self.btn_clear_selection = QPushButton("Clear Selection")

        control_panel.addWidget(self.btn_arm)
        control_panel.addWidget(self.btn_disarm)
        control_panel.addWidget(self.chk_indoor_mode)
        control_panel.addWidget(self.btn_restore_params)
        control_panel.addWidget(self.btn_select_all)
        control_panel.addWidget(self.btn_clear_selection)

        self.btn_arm.clicked.connect(self.cmd_arm)
        self.btn_disarm.clicked.connect(self.cmd_disarm)
        self.btn_restore_params.clicked.connect(self.cmd_restore_params)
        self.btn_takeoff.clicked.connect(self.cmd_takeoff)
        self.btn_land.clicked.connect(self.cmd_land)
        self.btn_guided_position.clicked.connect(self.cmd_guided_position)
        self.btn_guided_velocity.clicked.connect(self.cmd_guided_velocity)
        self.btn_indoor_takeoff.clicked.connect(self.cmd_indoor_takeoff)
        self.btn_indoor_land.clicked.connect(self.cmd_indoor_land)
        self.btn_indoor_auto.clicked.connect(self.cmd_indoor_auto)
        self.btn_select_all.clicked.connect(self.select_all_drones)
        self.btn_clear_selection.clicked.connect(self.clear_drone_selection)

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
        # QTextEdit をこのメソッド内でインポート（ファイル上部のインポートエラーを防ぐため）
        from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QLabel, QWidget
        
        layout = QVBoxLayout()
        
        self.raw_data_label = QLabel("Raw MAVLink Data (JSON-like format)")
        layout.addWidget(self.raw_data_label)
        
        # QLabel と QScrollArea の組み合わせをやめ、QTextEdit に変更
        self.raw_data_text = QTextEdit()
        self.raw_data_text.setReadOnly(True)  # 読み取り専用にする
        self.raw_data_text.setStyleSheet("font-family: monospace;") # 等幅フォント
        
        layout.addWidget(self.raw_data_text)
        
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def get_selected_system_id(self):
        ids = self.get_selected_system_ids()
        return ids[0] if ids else None

    def get_selected_system_ids(self):
        selected_items = self.drone_list.selectedItems()
        if not selected_items:
            return []
        system_ids = []
        for item in selected_items:
            try:
                system_ids.append(int(item.text()))
            except ValueError:
                continue
        return system_ids

    def select_all_drones(self):
        self.drone_list.selectAll()

    def clear_drone_selection(self):
        self.drone_list.clearSelection()

    def _on_drone_selected(self):
        """Called when drone selection changes"""
        if hasattr(self, '_update_dashboard'):
                self._update_dashboard()

    def cmd_arm(self):
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        if self.dispatcher:
            # GPS不要モードがチェックされていれば STABILIZE(0)
            mode = 0 if self.chk_indoor_mode.isChecked() else None
            for sysid in system_ids:
                logger.info(f"ARM command sent to drone {sysid}")
                self.dispatcher.arm(sysid, component_id=1, mode=mode)

    def cmd_disarm(self):
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        if self.dispatcher:
            for sysid in system_ids:
                logger.info(f"DISARM command sent to drone {sysid}")
                self.dispatcher.disarm(sysid, component_id=1)

    def cmd_indoor_takeoff(self):
        """室内離陸: RC_CHANNELS_OVERRIDE でスロットル上昇"""
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        guided = getattr(self.dispatcher, 'guided', None)
        if not guided:
            QMessageBox.warning(self, "Warning", "Guided control is not available.")
            return
        for sysid in system_ids:
            if not self._is_armed(sysid):
                QMessageBox.warning(self, "Warning", f"Drone {sysid} is not armed.")
                continue
            logger.info(f"Indoor takeoff for drone {sysid}")
            guided.indoor_takeoff(sysid, component_id=1, throttle_pct=65)

    def cmd_indoor_land(self):
        """室内着陸: RC_CHANNELS_OVERRIDE でスロットル最小"""
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        guided = getattr(self.dispatcher, 'guided', None)
        if not guided:
            QMessageBox.warning(self, "Warning", "Guided control is not available.")
            return
        for sysid in system_ids:
            logger.info(f"Indoor land for drone {sysid}")
            guided.indoor_land(sysid, component_id=1)

    def cmd_indoor_auto(self):
        """自動屋内テスト: 離陸→1m→5秒ホバリング→着陸"""
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        guided = getattr(self.dispatcher, 'guided', None)
        if not guided:
            QMessageBox.warning(self, "Warning", "Guided control is not available.")
            return
        for sysid in system_ids:
            if not self._is_armed(sysid):
                QMessageBox.warning(self, "Warning", f"Drone {sysid} is not armed.")
                continue
            logger.info(f"Starting indoor auto test for drone {sysid}")
            guided.indoor_test_sequence(sysid, component_id=1)

    def cmd_restore_params(self):
        """屋内モードで変更したパラメータを安全なデフォルトに戻す"""
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        if not self.dispatcher:
            return
        for sysid in system_ids:
            logger.info(f"Restoring arm params for drone {sysid}")
            self.dispatcher.restore_arm_params(sysid, component_id=1)
        QMessageBox.information(self, "パラメータ復元",
            f"ARMING_CHECK=1, AHRS_EKF_TYPE=3, FS_THR_ENABLE=1 に戻しました")

    def _is_armed(self, system_id):
        hb = self.telemetry_store.get_heartbeat(system_id)
        if not hb:
            return False
        try:
            return (hb.base_mode & 0x80) != 0
        except Exception:
            return False

    def cmd_takeoff(self):
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        if self.dispatcher:
            altitude = float(self.takeoff_altitude_spin.value())
            for sysid in system_ids:
                if not self._is_armed(sysid):
                    QMessageBox.warning(self, "Warning", f"Drone {sysid} is not armed.")
                    continue
                logger.info(f"TAKEOFF command sent to drone {sysid} at {altitude}m")
                self.dispatcher.takeoff(sysid, component_id=1, altitude=altitude)

    def cmd_land(self):
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return
        if self.dispatcher:
            descent_rate = float(self.land_descent_rate_spin.value())
            for sysid in system_ids:
                logger.info(f"LAND command sent to drone {sysid} (descent_rate={descent_rate})")
                self.dispatcher.land(sysid, component_id=1, descent_rate=descent_rate)

    def cmd_guided_position(self):
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return

        guided = getattr(self.dispatcher, 'guided', None)
        if not guided:
            QMessageBox.warning(self, "Warning", "Guided control is not available.")
            return

        north = float(self.guided_north_spin.value())
        east = float(self.guided_east_spin.value())
        down = float(self.guided_down_spin.value())
        yaw = float(self.guided_yaw_spin.value())
        for sysid in system_ids:
            logger.info(f"Guided position sent to drone {sysid}: NED=({north}, {east}, {down}), yaw={yaw}")
            guided.set_position_target_local_ned(sysid, component_id=1, x=north, y=east, z=down, yaw=yaw)

    def cmd_guided_velocity(self):
        system_ids = self.get_selected_system_ids()
        if not system_ids:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return

        guided = getattr(self.dispatcher, 'guided', None)
        if not guided:
            QMessageBox.warning(self, "Warning", "Guided control is not available.")
            return

        vx = float(self.guided_vx_spin.value())
        vy = float(self.guided_vy_spin.value())
        vz = float(self.guided_vz_spin.value())
        yaw = float(self.guided_yaw_spin.value())
        for sysid in system_ids:
            logger.info(f"Guided velocity sent to drone {sysid}: vel=({vx}, {vy}, {vz}), yaw={yaw}")
            guided.set_velocity_target_local_ned(sysid, component_id=1, vx=vx, vy=vy, vz=vz, yaw=yaw)

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
            self.gui_signals.update_command_status.emit()
        
        def on_timeout(system_id, command_id, description):
            """Called when command times out."""
            self.last_command_status[(system_id, command_id)] = {
                'status': 'TIMEOUT',
                'time': time.time()
            }
            logger.warning(f"Command TIMEOUT: system_id={system_id}, {description}")
            self.gui_signals.show_warning.emit("Command Timeout", f"Command {description} timed out on drone {system_id}")
            self.gui_signals.update_command_status.emit()
        
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
                self.gui_signals.show_warning.emit("Connection Error", f"{error_type}\n{message}")
            
            self.gui_signals.update_connection_status.emit()
        
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
        self.update_rtk_status_from_reader()

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
            
            # Update GPS Status (from GPS_RAW_INT for fix_type & satellites)
            gps_raw = self.telemetry_store.get_gps_raw(sysid)
            if gps_raw:
                try:
                    fix_type = getattr(gps_raw, 'fix_type', -1)
                    fix_names = {
                        0: "NO_GPS", 1: "NO_FIX", 2: "2D_FIX", 3: "3D_FIX",
                        4: "DGPS", 5: "RTK_FLOAT", 6: "RTK_FIXED",
                        7: "STATIC", 8: "PPP"
                    }
                    fix_name = fix_names.get(fix_type, f"UNKNOWN({fix_type})")
                    # Color-code: green for good fix, yellow for partial, red for none
                    if fix_type >= 5:   # RTK_FLOAT or RTK_FIXED
                        color = "green"
                    elif fix_type >= 3:  # 3D_FIX or DGPS
                        color = "orange"
                    else:
                        color = "red"
                    self.gps_fix_label.setText(
                        f'<span style="color:{color};font-weight:bold">{fix_name}</span>'
                    )

                    num_sats = getattr(gps_raw, 'satellites_visible', 0)
                    self.gps_satellites_label.setText(f"{num_sats} satellites")

                    hdop = getattr(gps_raw, 'eph', 0) / 100.0  # cm -> m
                    self.gps_hdop_label.setText(f"{hdop:.2f} m")
                except Exception as e:
                    logger.debug(f"Error processing GPS_RAW_INT: {e}")
            elif sys_status:
                # Fallback: get satellite count from SYS_STATUS
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
        # 現在Raw Dataタブを開いていない場合は、処理をスキップして負荷を減らす
        if self.tab_widget.currentWidget() != self.raw_data_widget:
            return

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
            raw_text = f"=== System ID: {sysid} Latest MAVLink Data ===\n\n"
            
            # すべてのメッセージ種類をループ処理
            for msg_type, msg in sorted(messages.items()):
                # pymavlinkのオブジェクトを辞書（dict）形式に変換
                if hasattr(msg, 'to_dict'):
                    msg_dict = msg.to_dict()
                    # 不要な 'mavpackettype' キーを削除（見やすくするため）
                    msg_dict.pop('mavpackettype', None)
                    
                    # 辞書の中身を見やすい文字列に整形
                    formatted_data = "\n".join([f"  {k}: {v}" for k, v in msg_dict.items()])
                    raw_text += f"[{msg_type}]\n{formatted_data}\n\n"
                else:
                    # to_dict がない場合はそのまま文字列として表示
                    raw_text += f"[{msg_type}]\n  {str(msg)}\n\n"
            
            # 1. 現在のスクロール位置を記憶する
            scrollbar = self.raw_data_text.verticalScrollBar()
            current_scroll_pos = scrollbar.value()
            
            # 2. テキストを更新する
            self.raw_data_text.setText(raw_text)
            
            # 3. スクロール位置を元に戻す
            scrollbar.setValue(current_scroll_pos)
            
            # (オプション) 等幅フォントにして数値を見やすくする
            self.raw_data_text.setStyleSheet("font-family: monospace;")
            
        except Exception as e:
            logger.debug(f"Error updating raw data: {e}")

    def update_rtk_status(self, status):
        """Update RTK status indicator"""
        self.rtk_status_label.setText(f"RTK Status: {status}")

    def _show_warning_dialog(self, title: str, message: str):
        """Show warning dialog (thread-safe slot)"""
        QMessageBox.warning(self, title, message)
    
    def _show_error_dialog(self, title: str, message: str):
        """Show error dialog (thread-safe slot)"""
        QMessageBox.critical(self, title, message)

    def update_rtk_status_from_reader(self):
        if not self.rtcm_reader:
            return
        try:
            stats = getattr(self.rtcm_reader, 'stats', {})
            status = (
                f"enabled={getattr(self.rtcm_reader, 'enabled', False)} "
                f"messages={stats.get('messages_received', 0)} "
                f"connections={stats.get('connections', 0)} "
                f"reconnects={stats.get('reconnects', 0)}"
            )
            self.update_rtk_status(status)
        except Exception as e:
            logger.debug(f"Error updating RTK status: {e}")
