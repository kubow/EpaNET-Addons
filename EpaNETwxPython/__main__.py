"""
wxPython GUI for EPANET

This module provides a wxPython-based GUI for EPANET network analysis.
"""

import wx
from pathlib import Path
import sys
import matplotlib
matplotlib.use('WXAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure

# Add parent directory to path to import epanet_wrapper
sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_wrapper import EpanetWrapper


class NetworkPlotPanel(wx.Panel):
    """Panel for displaying network plots."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self, -1, self.figure)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, wx.EXPAND)
        self.SetSizer(sizer)
    
    def plot_network(self, epanet_wrapper):
        """Plot the network using the epanet wrapper."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        try:
            epanet_wrapper.plot_network(ax=ax)
            self.canvas.draw()
        except Exception as e:
            wx.MessageBox(f"Visualization error: {e}", "Error", wx.OK | wx.ICON_ERROR)


class EpanetWxApp(wx.Frame):
    """Main wxPython application for EPANET."""
    
    def __init__(self):
        super().__init__(None, title="EPANET wxPython GUI", size=(800, 600))
        self.epanet = EpanetWrapper()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Load file button
        load_btn = wx.Button(panel, label="Load .inp File")
        load_btn.Bind(wx.EVT_BUTTON, self.load_file)
        vbox.Add(load_btn, 0, wx.ALL | wx.EXPAND, 5)
        
        # Run simulation button
        self.run_btn = wx.Button(panel, label="Run Simulation")
        self.run_btn.Bind(wx.EVT_BUTTON, self.run_simulation)
        self.run_btn.Enable(False)
        vbox.Add(self.run_btn, 0, wx.ALL | wx.EXPAND, 5)
        
        # Status label
        self.status_label = wx.StaticText(panel, label="No file loaded.")
        self.status_label.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        vbox.Add(self.status_label, 0, wx.ALL | wx.CENTER, 5)
        
        # Network plot panel
        self.plot_panel = NetworkPlotPanel(panel)
        vbox.Add(self.plot_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        panel.SetSizer(vbox)
        self.Centre()
    
    def load_file(self, event):
        """Load an EPANET input file."""
        with wx.FileDialog(self, "Open EPANET File", wildcard="EPANET Input Files (*.inp)|*.inp",
                          style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            
            file_path = fileDialog.GetPath()
            try:
                inp_path = Path(file_path)
                self.epanet.load_file(inp_path)
                
                file_name = self.epanet.get_file_name()
                self.status_label.SetLabel(f"Loaded: {file_name}")
                self.run_btn.Enable(True)
                self.plot_panel.plot_network(self.epanet)
            except Exception as e:
                wx.MessageBox(f"Failed to load file: {e}", "Error", wx.OK | wx.ICON_ERROR)
    
    def run_simulation(self, event):
        """Run the EPANET simulation."""
        if not self.epanet.is_loaded():
            wx.MessageBox("No file loaded!", "Warning", wx.OK | wx.ICON_WARNING)
            return
        
        try:
            self.epanet.run_simulation()
            wx.MessageBox("Simulation completed!", "Success", wx.OK | wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(f"Simulation error: {e}", "Error", wx.OK | wx.ICON_ERROR)


def main():
    """Main entry point."""
    app = wx.App()
    frame = EpanetWxApp()
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()

