"""
Real-time telemetry plotter for NAMED_VALUE_FLOAT data
"""
import logging
from collections import defaultdict, deque
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)

class TelemetryPlotter(QWidget):
    """Real-time graph widget for telemetry data"""
    
    def __init__(self, telemetry_store, max_points=500):
        super().__init__()
        self.telemetry_store = telemetry_store
        self.max_points = max_points
        
        # Data storage: {system_id: {field_name: deque of values}}
        self.data_history = defaultdict(lambda: defaultdict(lambda: deque(maxlen=self.max_points)))
        self.timestamps = defaultdict(lambda: defaultdict(lambda: deque(maxlen=self.max_points)))
        self.curves = {}
        
        # UI Setup
        layout = QVBoxLayout()
        
        # Controls
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Drone:"))
        self.drone_combo = QComboBox()
        control_layout.addWidget(self.drone_combo)
        
        control_layout.addWidget(QLabel("Field:"))
        self.field_combo = QComboBox()
        control_layout.addWidget(self.field_combo)
        
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_data)
        control_layout.addWidget(self.btn_clear)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # Graph
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Value')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.plot_widget.setTitle('Named Value Float - Real-Time Plot')
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(True, True)
        self.plot_widget.addLegend()
        layout.addWidget(self.plot_widget)
        
        self.setLayout(layout)
        
        # Curve for current plot
        self.curve = self.plot_widget.plot(pen='b')
        
        # Connect combo box signals
        self.drone_combo.currentTextChanged.connect(self._on_drone_changed)
        self.field_combo.currentTextChanged.connect(self._on_field_changed)
    
    def update_data(self, telemetry_store):
        """Update plotter with latest data from telemetry store"""
        self.telemetry_store = telemetry_store
        self.data_history.clear()
        self.timestamps.clear()
        
        all_data = telemetry_store.get_all()
        for sysid, messages in all_data.items():
            history = messages.get('NAMED_VALUE_FLOAT_HISTORY', {})
            for field_name, entries in history.items():
                try:
                    for entry in entries[-self.max_points:]:
                        self.data_history[sysid][field_name].append(entry.get('value', 0.0))
                        self.timestamps[sysid][field_name].append(entry.get('timestamp', 0.0) / 1e6)
                except Exception as e:
                    logger.debug(f"Error extracting NAMED_VALUE_FLOAT history: {e}")
        
        # Update combo boxes
        self._update_combo_boxes()
        
        # Update plot
        self._update_plot()
    
    def _update_combo_boxes(self):
        """Update drone and field combo boxes"""
        current_drone = self.drone_combo.currentText()
        current_field = self.field_combo.currentText()
        
        # Get available drones
        drones = sorted([str(sysid) for sysid in self.data_history.keys()])
        
        # Update drone combo
        self.drone_combo.blockSignals(True)
        self.drone_combo.clear()
        self.drone_combo.addItems(drones)
        if current_drone in drones:
            self.drone_combo.setCurrentText(current_drone)
        self.drone_combo.blockSignals(False)
        
        # Get available fields for selected drone
        if drones and current_drone in drones:
            sysid = int(current_drone)
            fields = ['All Fields'] + sorted(self.data_history[sysid].keys())
        else:
            fields = ['All Fields'] if drones else []
        
        # Update field combo
        self.field_combo.blockSignals(True)
        self.field_combo.clear()
        self.field_combo.addItems(fields)
        if current_field in fields:
            self.field_combo.setCurrentText(current_field)
        self.field_combo.blockSignals(False)
    
    def _on_drone_changed(self):
        """Called when drone selection changes"""
        # Update field combo based on new drone
        self._update_combo_boxes()
        self._update_plot()
    
    def _on_field_changed(self):
        """Called when field selection changes"""
        self._update_plot()
    
    def _update_plot(self):
        """Update plot with selected drone/field data"""
        try:
            drone_str = self.drone_combo.currentText()
            field_name = self.field_combo.currentText()
            
            if not drone_str or not field_name:
                self.plot_widget.clear()
                return
            
            sysid = int(drone_str)
            self.plot_widget.clear()
            self.plot_widget.addLegend()

            if field_name == 'All Fields':
                fields = sorted(self.data_history[sysid].keys())
            else:
                fields = [field_name]

            colors = ['b', 'r', 'g', 'c', 'm', 'y', 'w']
            for index, field in enumerate(fields):
                values = list(self.data_history[sysid][field])
                if not values:
                    continue
                x_data = list(range(len(values)))
                pen = pg.mkPen(colors[index % len(colors)], width=2)
                self.plot_widget.plot(x_data, values, pen=pen, name=field)

            self.plot_widget.setTitle(f'Drone {sysid} - {field_name}')
        except Exception as e:
            logger.error(f"Error updating plot: {e}")
    
    def clear_data(self):
        """Clear all stored data"""
        self.data_history.clear()
        self.timestamps.clear()
        self._update_combo_boxes()
        self._update_plot()
