from PySide6.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import QTimer

class MainWindow(QMainWindow):
    def __init__(self, telemetry_store):
        super().__init__()
        self.telemetry_store = telemetry_store
        self.setWindowTitle("GCS Telemetry")
        self.label = QLabel("NAMED_VALUE_FLOAT: 未受信")
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self._setup_timer()

    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_label)
        self.timer.start(1000)

    def update_label(self):
        all_data = self.telemetry_store.get_all()
        text = "NAMED_VALUE_FLOAT: 未受信"
        for sysid, messages in all_data.items():
            nvf = messages.get('NAMED_VALUE_FLOAT')
            if nvf:
                text = f"[system_id={sysid}] NAMED_VALUE_FLOAT: {nvf}"
        self.label.setText(text)
