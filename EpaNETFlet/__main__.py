"""
Flet GUI for EPANET

This module provides a Flet-based GUI for EPANET network analysis.
Flet is a Flutter-based framework for building cross-platform apps.
"""

import flet as ft
from pathlib import Path
import sys
import matplotlib.pyplot as plt
import io
import base64

# Add parent directory to path to import epanet_wrapper
sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_wrapper import EpanetWrapper


def main(page: ft.Page):
    """Main Flet application."""
    page.title = "EPANET Flet GUI"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    
    epanet = EpanetWrapper()
    
    # Status text
    status_text = ft.Text("No file loaded.", size=16)
    
    # File picker
    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            file_path = Path(e.files[0].path)
            try:
                epanet.load_file(file_path)
                status_text.value = f"Loaded: {file_path.name}"
                run_btn.disabled = False
                display_btn.disabled = False
                page.update()
            except Exception as ex:
                status_text.value = f"Error: {ex}"
                page.update()
    
    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)
    
    # Buttons
    load_btn = ft.ElevatedButton(
        "Load .inp File",
        on_click=lambda _: file_picker.pick_files(
            allowed_extensions=["inp"],
            dialog_title="Select EPANET File"
        )
    )
    
    run_btn = ft.ElevatedButton(
        "Run Simulation",
        disabled=True,
        on_click=lambda _: run_simulation(epanet, status_text, page)
    )
    
    display_btn = ft.ElevatedButton(
        "Display Network",
        disabled=True,
        on_click=lambda _: display_network(epanet, status_text, page)
    )
    
    # Image for network plot
    network_image = ft.Image(src_base64="", width=800, height=600, visible=False)
    
    def run_simulation(epanet_wrapper, status, page_ref):
        """Run EPANET simulation."""
        if not epanet_wrapper.is_loaded():
            status.value = "No file loaded!"
            page_ref.update()
            return
        
        try:
            epanet_wrapper.run_simulation()
            status.value = "Simulation completed!"
            page_ref.show_snack_bar(ft.SnackBar(ft.Text("Simulation completed successfully!")))
        except Exception as e:
            status.value = f"Simulation error: {e}"
        page_ref.update()
    
    def display_network(epanet_wrapper, status, page_ref):
        """Display network visualization."""
        if not epanet_wrapper.is_loaded():
            status.value = "No file loaded!"
            page_ref.update()
            return
        
        try:
            fig, ax = plt.subplots(figsize=(10, 8))
            epanet_wrapper.plot_network(ax=ax)
            
            # Convert to base64
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png')
            img_buffer.seek(0)
            img_base64 = base64.b64encode(img_buffer.read()).decode()
            plt.close(fig)
            
            network_image.src_base64 = img_base64
            network_image.visible = True
            page_ref.update()
        except Exception as e:
            status.value = f"Visualization error: {e}"
            page_ref.update()
    
    # Layout
    page.add(
        ft.Container(
            content=ft.Column([
                ft.Text("EPANET Network Analysis", size=24, weight=ft.FontWeight.BOLD),
                status_text,
                ft.Row([load_btn, run_btn, display_btn], alignment=ft.MainAxisAlignment.CENTER),
                network_image
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=20
        )
    )


if __name__ == '__main__':
    ft.app(target=main)

