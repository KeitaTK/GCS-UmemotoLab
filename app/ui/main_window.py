from PySide6.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QListWidget, QPushButton, QMessageBox
from PySide6.QtCore import QTimer

class MainWindow(QMainWindow):
    def __init__(self, telemetry_store, dispatcher=None):
        super().__init__()
        self.telemetry_store = telemetry_store
        self.dispatcher = dispatcher
        self.setWindowTitle("GCS Telemetry")

        # --- UI構成 ---
        central = QWidget()
        main_layout = QHBoxLayout()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # ドローンリスト
        from PySide6.QtWidgets import QListWidget, QPushButton
        self.drone_list = QListWidget()
        self.drone_list.setMinimumWidth(200)
        main_layout.addWidget(self.drone_list)

        # テレメトリパネル
        telemetry_panel = QVBoxLayout()
        telemetry_widget = QWidget()
        telemetry_widget.setLayout(telemetry_panel)
        main_layout.addWidget(telemetry_widget)

        # RTKステータスインジケーター
        self.rtk_status_label = QLabel("RTK Status: Unknown")
        telemetry_panel.addWidget(self.rtk_status_label)

        # NAMED_VALUE_FLOATラベル（既存）
        self.label = QLabel("NAMED_VALUE_FLOAT: 未受信")
        telemetry_panel.addWidget(self.label)

        # NAMED_VALUE_FLOATグラフのプレースホルダー
        self.named_value_float_graph = QLabel("Debug Graph Placeholder")
        telemetry_panel.addWidget(self.named_value_float_graph)

        # テスト用ボタン（ドローンリスト更新）
        update_btn = QPushButton("Update Drone List (Test)")
        update_btn.clicked.connect(self._test_update_drone_list)
        telemetry_panel.addWidget(update_btn)

        # 制御コンポーネント（コマンド）パネル
        control_panel = QHBoxLayout()
        telemetry_panel.addLayout(control_panel)

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

        self._setup_timer()

    def get_selected_system_id(self):
        selected_items = self.drone_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
            return None
        sysid_str = selected_items[0].text()
        try:
            return int(sysid_str)
        except ValueError:
            QMessageBox.warning(self, "Warning", f"Invalid drone ID: {sysid_str}")
            return None

    def cmd_arm(self):
        sysid = self.get_selected_system_id()
        if sysid and self.dispatcher:
            self.dispatcher.arm(sysid, component_id=1)

    def cmd_disarm(self):
        sysid = self.get_selected_system_id()
        if sysid and self.dispatcher:
            self.dispatcher.disarm(sysid, component_id=1)

    def cmd_takeoff(self):
        sysid = self.get_selected_system_id()
        if sysid and self.dispatcher:
            self.dispatcher.takeoff(sysid, component_id=1, altitude=10.0)

    def cmd_land(self):
        sysid = self.get_selected_system_id()
        if sysid and self.dispatcher:
            self.dispatcher.land(sysid, component_id=1)

    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_label)
        self.timer.start(1000)

    def update_label(self):
        all_data = self.telemetry_store.get_all()
        text = "NAMED_VALUE_FLOAT: 未受信"
        drone_ids = []
        for sysid, messages in all_data.items():
            drone_ids.append(str(sysid))
            nvf = messages.get('NAMED_VALUE_FLOAT')
            if nvf:
                text = f"[system_id={sysid}] NAMED_VALUE_FLOAT: {nvf}"
        self.label.setText(text)
        # ドローンリストの更新（選択状態を維持するため、存在しないIDだけを追加）
        existing_items = [self.drone_list.item(i).text() for i in range(self.drone_list.count())]
        for drone_id in drone_ids:
            if drone_id not in existing_items:
                self.drone_list.addItem(drone_id)

    def update_rtk_status(self, status):
        self.rtk_status_label.setText(f"RTK Status: {status}")

    def update_named_value_float_graph(self, value):
        # 仮実装: グラフラベルに値を表示
        self.named_value_float_graph.setText(f"Debug Graph: {value}")

    def _test_update_drone_list(self):
        # テスト用: ドローンリストを更新
        self.drone_list.clear()
        for drone in ["Drone1", "Drone2", "Drone3"]:
            self.drone_list.addItem(drone)
