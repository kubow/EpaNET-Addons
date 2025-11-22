"""
Kivy GUI for EPANET

This module provides a Kivy-based GUI for EPANET network analysis.
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from pathlib import Path
import sys

# Add parent directory to path to import epanet_wrapper
sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_wrapper import EpanetWrapper


class EpanetKivyApp(App):
    """Main Kivy application for EPANET."""
    
    def build(self):
        self.epanet = EpanetWrapper()
        
        # Main layout
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Title
        title = Label(text='EPANET Kivy GUI', size_hint_y=None, height=50)
        layout.add_widget(title)
        
        # Status label
        self.status_label = Label(text='No file loaded.', size_hint_y=None, height=30)
        layout.add_widget(self.status_label)
        
        # Load file button
        load_btn = Button(text='Load .inp File', size_hint_y=None, height=40)
        load_btn.bind(on_press=self.load_file)
        layout.add_widget(load_btn)
        
        # Run simulation button
        self.run_btn = Button(text='Run Simulation', size_hint_y=None, height=40, disabled=True)
        self.run_btn.bind(on_press=self.run_simulation)
        layout.add_widget(self.run_btn)
        
        # Display network button
        self.display_btn = Button(text='Display Network', size_hint_y=None, height=40, disabled=True)
        self.display_btn.bind(on_press=self.display_network)
        layout.add_widget(self.display_btn)
        
        return layout
    
    def load_file(self, instance):
        """Open file chooser to load .inp file."""
        # Note: This is a simplified version. In a real implementation,
        # you would use a proper file chooser dialog
        popup = Popup(title='File Chooser',
                     content=Label(text='File chooser not fully implemented.\nUse file path input instead.'),
                     size_hint=(0.8, 0.4))
        popup.open()
        # TODO: Implement proper file chooser
    
    def run_simulation(self, instance):
        """Run the EPANET simulation."""
        if not self.epanet.is_loaded():
            self.show_error("No file loaded!")
            return
        
        try:
            self.epanet.run_simulation()
            self.show_success("Simulation completed!")
        except Exception as e:
            self.show_error(f"Simulation error: {e}")
    
    def display_network(self, instance):
        """Display the network visualization."""
        if not self.epanet.is_loaded():
            self.show_error("No file loaded!")
            return
        
        try:
            self.epanet.plot_network()
            self.show_success("Network displayed!")
        except Exception as e:
            self.show_error(f"Visualization error: {e}")
    
    def show_error(self, message):
        """Show error popup."""
        popup = Popup(title='Error',
                     content=Label(text=message),
                     size_hint=(0.8, 0.4))
        popup.open()
    
    def show_success(self, message):
        """Show success popup."""
        popup = Popup(title='Success',
                     content=Label(text=message),
                     size_hint=(0.8, 0.4))
        popup.open()


if __name__ == '__main__':
    EpanetKivyApp().run()

