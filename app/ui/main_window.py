from PySide6.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QListWidget, QPushButton
from PySide6.QtCore import QTimer

class MainWindow(QMainWindow):
    def __init__(self, telemetry_store):
        super().__init__()
        self.telemetry_store = telemetry_store
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

        self._setup_timer()

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
        # ドローンリスト更新
        self.drone_list.clear()
        for drone_id in drone_ids:
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
