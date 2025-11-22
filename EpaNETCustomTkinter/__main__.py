"""
CustomTkinter GUI for EPANET

This module provides a CustomTkinter-based GUI for EPANET network analysis.
CustomTkinter provides a modern, customizable look for Tkinter applications.
"""

import customtkinter as ctk
from pathlib import Path
import sys
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Add parent directory to path to import epanet_wrapper
sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_wrapper import EpanetWrapper

# Set appearance mode and color theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class EpanetCustomTkinterApp(ctk.CTk):
    """Main CustomTkinter application for EPANET."""
    
    def __init__(self):
        super().__init__()
        self.epanet = EpanetWrapper()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.title("EPANET CustomTkinter GUI")
        self.geometry("900x700")
        
        # Main container
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title_label = ctk.CTkLabel(main_frame, text="EPANET Network Analysis", 
                                  font=ctk.CTkFont(size=24, weight="bold"))
        title_label.pack(pady=10)
        
        # Status label
        self.status_label = ctk.CTkLabel(main_frame, text="No file loaded.", 
                                        font=ctk.CTkFont(size=14))
        self.status_label.pack(pady=10)
        
        # Buttons frame
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(pady=10)
        
        # Load file button
        self.load_button = ctk.CTkButton(button_frame, text="Load .inp File", 
                                         command=self.load_file, width=200)
        self.load_button.pack(side="left", padx=5)
        
        # Run simulation button
        self.run_button = ctk.CTkButton(button_frame, text="Run Simulation", 
                                        command=self.run_simulation, width=200,
                                        state="disabled")
        self.run_button.pack(side="left", padx=5)
        
        # Display network button
        self.display_button = ctk.CTkButton(button_frame, text="Display Network", 
                                           command=self.display_network, width=200,
                                           state="disabled")
        self.display_button.pack(side="left", padx=5)
        
        # Matplotlib Figure for Network Visualization
        self.figure, self.ax = plt.subplots(figsize=(8, 6))
        self.canvas = FigureCanvasTkAgg(self.figure, master=main_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=10)
    
    def load_file(self):
        """Load an EPANET input file."""
        from tkinter import filedialog
        
        file_path = filedialog.askopenfilename(filetypes=[("EPANET Input Files", "*.inp")])
        if file_path:
            try:
                inp_path = Path(file_path)
                self.epanet.load_file(inp_path)
                
                file_name = self.epanet.get_file_name()
                self.status_label.configure(text=f"Loaded: {file_name}")
                self.run_button.configure(state="normal")
                self.display_button.configure(state="normal")
                self.display_network()
            except Exception as e:
                self.status_label.configure(text=f"Error: {e}")
    
    def run_simulation(self):
        """Run the EPANET simulation."""
        if not self.epanet.is_loaded():
            self.status_label.configure(text="No file loaded!")
            return
        
        try:
            self.epanet.run_simulation()
            self.status_label.configure(text="Simulation completed!")
        except Exception as e:
            self.status_label.configure(text=f"Simulation error: {e}")
    
    def display_network(self):
        """Display the network visualization."""
        if not self.epanet.is_loaded():
            return
        
        try:
            self.ax.clear()
            self.epanet.plot_network(ax=self.ax)
            self.canvas.draw()
        except Exception as e:
            self.status_label.configure(text=f"Visualization error: {e}")


if __name__ == '__main__':
    app = EpanetCustomTkinterApp()
    app.mainloop()

