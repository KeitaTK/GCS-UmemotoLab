"""
Real-time telemetry plotter for numeric data fields
"""
import logging
from collections import defaultdict, deque
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFileDialog
from PySide6.QtCore import Qt, QRectF

logger = logging.getLogger(__name__)

class TelemetryPlotter(QWidget):
    """Real-time graph widget for telemetry data"""
    
    def __init__(self, telemetry_store, max_points=100):
        super().__init__()
        self.telemetry_store = telemetry_store
        self.max_points = max_points
        
        # データの保存形式: {system_id: { "MSG_TYPE.field_name": deque([...]) }}
        self.data_history = defaultdict(lambda: defaultdict(lambda: deque(maxlen=self.max_points)))
        
        # UI Setup
        layout = QVBoxLayout()
        
        # Controls
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Drone:"))
        self.drone_combo = QComboBox()
        control_layout.addWidget(self.drone_combo)
        
        control_layout.addWidget(QLabel("Data:"))
        self.field_combo = QComboBox()
        control_layout.addWidget(self.field_combo)
        
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_data)
        control_layout.addWidget(self.btn_clear)

        self.btn_save = QPushButton("Save Image")
        self.btn_save.clicked.connect(self.save_graph)
        control_layout.addWidget(self.btn_save)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # Graph
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Value')
        self.plot_widget.setLabel('bottom', 'Samples')
        self.plot_widget.setTitle('Telemetry Real-Time Plot')
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(True, True)
        self.plot_widget.addLegend()
        layout.addWidget(self.plot_widget)
        
        self.setLayout(layout)
        
        # Connect combo box signals
        self.drone_combo.currentTextChanged.connect(self._on_drone_changed)
        self.field_combo.currentTextChanged.connect(self._on_field_changed)
    
    def update_data(self, telemetry_store):
        """Update plotter with latest data from telemetry store"""
        all_data = telemetry_store.get_all()
        for sysid, messages in all_data.items():
            for msg_type, msg in messages.items():
                # 無視するメッセージ（文字列だけだったり、グラフ化に向かないもの）
                if msg_type in ['STATUSTEXT', 'HEARTBEAT', 'TIMESYNC', 'SYSTEM_TIME']:
                    continue
                
                # dictに変換して数値データのみを抽出
                if hasattr(msg, 'to_dict'):
                    msg_dict = msg.to_dict()
                    for key, value in msg_dict.items():
                        if isinstance(value, (int, float)):
                            field_path = f"{msg_type}.{key}"
                            self.data_history[sysid][field_path].append(value)
        
        self._update_combo_boxes()
        self._update_plot()
    
    def _update_combo_boxes(self):
        """Update drone and field combo boxes"""
        current_drone = self.drone_combo.currentText()
        current_field = self.field_combo.currentText()
        
        # Update drone combo
        drones = sorted([str(sysid) for sysid in self.data_history.keys()])
        self.drone_combo.blockSignals(True)
        self.drone_combo.clear()
        self.drone_combo.addItems(drones)
        if current_drone in drones:
            self.drone_combo.setCurrentText(current_drone)
        self.drone_combo.blockSignals(False)
        
        # Update field combo based on selected drone
        fields = []
        if drones and self.drone_combo.currentText():
            sysid = int(self.drone_combo.currentText())
            # 頻繁に使う項目を先頭に持ってくる（おすすめリスト）
            recommended = [
                'ATTITUDE.roll', 'ATTITUDE.pitch', 'ATTITUDE.yaw',
                'ATTITUDE.rollspeed', 'ATTITUDE.pitchspeed', 'ATTITUDE.yawspeed',
                'VFR_HUD.alt', 'VFR_HUD.airspeed',
                'BATTERY_STATUS.voltage_battery', 'BATTERY_STATUS.current_battery'
            ]
            
            all_fields = sorted(self.data_history[sysid].keys())
            
            # 存在するおすすめ項目を先頭に
            for rec in recommended:
                if rec in all_fields:
                    fields.append(rec)
            
            # 残りの項目を追加
            if fields:
                fields.append("--- Others ---")
            for f in all_fields:
                if f not in recommended:
                    fields.append(f)

        self.field_combo.blockSignals(True)
        self.field_combo.clear()
        self.field_combo.addItems(fields)
        if current_field in fields:
            self.field_combo.setCurrentText(current_field)
        self.field_combo.blockSignals(False)
    
    def _on_drone_changed(self):
        self._update_combo_boxes()
        self._update_plot()
    
    def _on_field_changed(self):
        self._update_plot()
    
    def _update_plot(self):
        """Update plot with selected drone/field data"""
        try:
            drone_str = self.drone_combo.currentText()
            field_name = self.field_combo.currentText()
            
            if not drone_str or not field_name or field_name == "--- Others ---":
                self.plot_widget.clear()
                self.plot_widget.setLabel('left', 'Value') # デフォルトに戻す
                return
            
            sysid = int(drone_str)
            self.plot_widget.clear()
            self.plot_widget.addLegend()

            # --- 縦軸のラベルを「roll」や「pitch」などに自動変更 ---
            display_label = field_name.split('.')[-1]
            self.plot_widget.setLabel('left', display_label)

            values = list(self.data_history[sysid][field_name])
            if values:
                x_data = list(range(len(values)))
                pen = pg.mkPen('b', width=2)
                self.plot_widget.plot(x_data, values, pen=pen, name=field_name)

            self.plot_widget.setTitle(f'Drone {sysid} - {field_name}')
        except Exception as e:
            logger.error(f"Error updating plot: {e}")
    
    def clear_data(self):
        """Clear all stored data"""
        self.data_history.clear()
        self._update_combo_boxes()
        self._update_plot()

    def save_graph(self):
        """Export the current plot to an image file"""
        try:
            # 選択中のデータ名からデフォルトファイル名を作成 (例: ATTITUDE.roll -> roll_response.png)
            current_field = self.field_combo.currentText()
            if current_field and current_field != "--- Others ---":
                short_name = current_field.split('.')[-1]
                default_filename = f"{short_name}_response.png"
            else:
                default_filename = "drone_telemetry.png"

            import os
            # MacやWindowsの「ダウンロード」フォルダのパスを自動取得
            download_dir = os.path.expanduser('~/Downloads')
            # フォルダのパスとファイル名を結合
            default_filepath = os.path.join(download_dir, default_filename)

            # 保存先のファイル名と形式を選択するダイアログを表示（PDFを削除）
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Graph Image",
                default_filepath,
                "PNG Image (*.png);;SVG Vector (*.svg)"
            )
            
            if file_path:
                # 1. SVG形式での保存処理（拡大してもぼやけないベクター形式）
                if file_path.endswith('.svg'):
                    exporter = pg.exporters.SVGExporter(self.plot_widget.plotItem)
                    exporter.export(file_path)

                # 2. PNG形式での保存処理（通常の画像形式）
                else:
                    exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
                    # 背景を白に設定して見やすくする
                    exporter.parameters()['background'] = 'w'
                    exporter.export(file_path)
                
                logger.info(f"Graph successfully saved to {file_path}")
                
        except Exception as e:
            logger.error(f"Error saving graph: {e}")