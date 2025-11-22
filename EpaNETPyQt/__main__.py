"""
PyQt/PySide GUI for EPANET

This module provides a PyQt/PySide-based GUI for EPANET network analysis.
"""

import sys
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QLabel, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Add parent directory to path to import epanet_wrapper
sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_wrapper import EpanetWrapper


class NetworkPlotWidget(QWidget):
    """Widget for displaying network plots."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
    
    def plot_network(self, epanet_wrapper):
        """Plot the network using the epanet wrapper."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        try:
            epanet_wrapper.plot_network(ax=ax)
            self.canvas.draw()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Visualization error: {e}")


class EpanetPyQtApp(QMainWindow):
    """Main PyQt application for EPANET."""
    
    def __init__(self):
        super().__init__()
        self.epanet = EpanetWrapper()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("EPANET PyQt GUI")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # Load file button
        self.load_button = QPushButton("Load .inp File")
        self.load_button.clicked.connect(self.load_file)
        layout.addWidget(self.load_button)
        
        # Run simulation button
        self.run_button = QPushButton("Run Simulation")
        self.run_button.clicked.connect(self.run_simulation)
        self.run_button.setEnabled(False)
        layout.addWidget(self.run_button)
        
        # Status label
        self.status_label = QLabel("No file loaded.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Network plot widget
        self.plot_widget = NetworkPlotWidget()
        layout.addWidget(self.plot_widget)
    
    def load_file(self):
        """Load an EPANET input file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open EPANET File", "", "EPANET Input Files (*.inp)"
        )
        
        if file_path:
            try:
                inp_path = Path(file_path)
                self.epanet.load_file(inp_path)
                
                file_name = self.epanet.get_file_name()
                self.status_label.setText(f"Loaded: {file_name}")
                self.run_button.setEnabled(True)
                self.plot_widget.plot_network(self.epanet)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file: {e}")
    
    def run_simulation(self):
        """Run the EPANET simulation."""
        if not self.epanet.is_loaded():
            QMessageBox.warning(self, "Warning", "No file loaded!")
            return
        
        try:
            self.epanet.run_simulation()
            QMessageBox.information(self, "Success", "Simulation completed!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Simulation error: {e}")


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = EpanetPyQtApp()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

