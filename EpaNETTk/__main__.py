import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sys

# Add parent directory to path to import epanet_wrapper
sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_wrapper import EpanetWrapper


class EPANETGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("EPANET GUI - Network Analysis")
        self.root.geometry("1200x800")
        
        # Initialize EPANET wrapper
        self.epanet = EpanetWrapper()
        self.simulation_run = False
        
        # Create main container
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel for controls
        left_panel = tk.Frame(main_frame, width=250)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)
        
        # Right panel for visualization
        right_panel = tk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # === LEFT PANEL CONTROLS ===
        
        # Toolbox frame (compact)
        toolbox_frame = tk.LabelFrame(left_panel, text="Toolbox", padx=5, pady=5)
        toolbox_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Top row: Open and Run buttons
        btn_row1 = tk.Frame(toolbox_frame)
        btn_row1.pack(fill=tk.X, pady=2)
        self.load_button = tk.Button(btn_row1, text="Open", command=self.load_file, width=10)
        self.load_button.pack(side=tk.LEFT, padx=2)
        self.run_button = tk.Button(btn_row1, text="Run", command=self.run_simulation, 
                                    state=tk.DISABLED, width=10)
        self.run_button.pack(side=tk.LEFT, padx=2)
        
        # Second row: Show Links and Show Labels
        btn_row2 = tk.Frame(toolbox_frame)
        btn_row2.pack(fill=tk.X, pady=2)
        self.info_button = tk.Button(btn_row2, text="Show Links", 
                                     command=self.show_network_info, width=10)
        self.info_button.pack(side=tk.LEFT, padx=2)
        self.show_labels_var = tk.BooleanVar(value=False)
        show_labels_cb = tk.Checkbutton(btn_row2, text="Labels", variable=self.show_labels_var,
                                        command=self.update_plot)
        show_labels_cb.pack(side=tk.LEFT, padx=2)
        
        # Third row: EPyT switch
        btn_row3 = tk.Frame(toolbox_frame)
        btn_row3.pack(fill=tk.X, pady=2)
        self.use_epyt_native_var = tk.BooleanVar(value=False)
        tk.Checkbutton(btn_row3, text="EPyT Native", 
                      variable=self.use_epyt_native_var).pack(anchor=tk.W)
        
        # Status label (compact)
        self.status_label = tk.Label(toolbox_frame, text="No file loaded.", 
                                     wraplength=200, justify=tk.LEFT, font=("Arial", 8))
        self.status_label.pack(pady=2)
        
        # Statistics frame
        stats_frame = tk.LabelFrame(left_panel, text="Network Stats", padx=5, pady=5)
        stats_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.stats_text = tk.Text(stats_frame, height=4, width=25, wrap=tk.WORD, state=tk.DISABLED, font=("Arial", 9))
        self.stats_text.pack()
        
        # Visualization options
        viz_frame = tk.LabelFrame(left_panel, text="Visualization", padx=5, pady=5)
        viz_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Plot type selection (compact)
        self.plot_type_var = tk.StringVar(value="topology")
        plot_types = [
            ("Topology", "topology"),
            ("Elevation", "elevation"),
            ("Pressure", "pressure"),
            ("Flow", "flow"),
            ("Quality", "quality")
        ]
        for text, value in plot_types:
            rb = tk.Radiobutton(viz_frame, text=text, variable=self.plot_type_var, 
                               value=value, command=self.update_plot, font=("Arial", 9))
            rb.pack(anchor=tk.W)
        
        # Plot button
        self.plot_button = tk.Button(viz_frame, text="Update Plot", command=self.update_plot, 
                                    state=tk.DISABLED, width=20)
        self.plot_button.pack(pady=3)
        
        # Time series frame (at bottom)
        ts_frame = tk.LabelFrame(left_panel, text="Time Series", padx=5, pady=5)
        ts_frame.pack(fill=tk.X)
        
        tk.Label(ts_frame, text="Type:", font=("Arial", 9)).pack(anchor=tk.W)
        self.ts_type_var = tk.StringVar(value="pressure")
        ts_types = [("Pressure", "pressure"), ("Velocity", "velocity"), ("Flow", "flow")]
        for text, value in ts_types:
            rb = tk.Radiobutton(ts_frame, text=text, variable=self.ts_type_var, value=value, font=("Arial", 9))
            rb.pack(anchor=tk.W)
        
        tk.Label(ts_frame, text="IDs:", font=("Arial", 9)).pack(anchor=tk.W, pady=(3, 0))
        self.ts_indices_entry = tk.Entry(ts_frame, width=18, font=("Arial", 9))
        self.ts_indices_entry.pack(pady=2)
        self.ts_indices_entry.insert(0, "J1,J3,J5")
        tk.Label(ts_frame, text="(e.g., J1,J3)", font=("Arial", 7)).pack(anchor=tk.W)
        
        self.ts_button = tk.Button(ts_frame, text="Plot", command=self.plot_time_series,
                                   state=tk.DISABLED, width=18)
        self.ts_button.pack(pady=3)
        
        # === RIGHT PANEL VISUALIZATION ===
        
        # Matplotlib Figure for Network Visualization
        self.figure, self.ax = plt.subplots(figsize=(10, 8))
        # Set fixed margins to prevent canvas shrinking - keep these constant
        self.figure.subplots_adjust(left=0.05, right=0.92, top=0.95, bottom=0.05)
        self.canvas = FigureCanvasTkAgg(self.figure, master=right_panel)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Store original subplot params to restore after each plot
        self.original_subplot_params = self.figure.subplotpars
        
        # Store network graph and positions for click detection
        self.network_graph = None
        self.network_positions = None
        self.network_node_info = {}  # Store node info (index, ID, etc.)
        self.network_link_info = {}  # Store link info (index, ID, etc.)
        
        # Connect click event
        self.canvas.mpl_connect('button_press_event', self.on_plot_click)
        
        # Annotation for callout
        self.annotation = None
    
    def load_file(self):
        """Load an EPANET input file."""
        file_path = filedialog.askopenfilename(filetypes=[("EPANET Input Files", "*.inp")])
        if file_path:
            try:
                inp_path = Path(file_path)
                self.epanet.load_file(inp_path)
                
                # Update UI
                file_name = self.epanet.get_file_name()
                self.status_label.config(text=f"Loaded: {file_name}")
                self.run_button.config(state=tk.NORMAL)
                self.plot_button.config(state=tk.NORMAL)
                self.ts_button.config(state=tk.NORMAL)
                self.info_button.config(state=tk.NORMAL)
                self.simulation_run = False
                
                # Update statistics
                self.update_statistics()
                
                # Display initial network
                self.update_plot()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {e}")
    
    def run_simulation(self):
        """Run the EPANET simulation."""
        if not self.epanet.is_loaded():
            messagebox.showerror("Error", "No file selected!")
            return
        
        try:
            self.status_label.config(text="Running simulation...")
            self.root.update()
            
            self.epanet.run_simulation()
            self.simulation_run = True
            
            self.status_label.config(text="Simulation completed!")
            messagebox.showinfo("Success", "Simulation completed!")
            
            # Update statistics and plot
            self.update_statistics()
            self.update_plot()
        except Exception as e:
            self.status_label.config(text="Simulation failed")
            messagebox.showerror("Error", f"EPANET Error: {e}")
    
    def update_statistics(self):
        """Update the statistics display."""
        if not self.epanet.is_loaded():
            return
        
        try:
            stats = self.epanet.get_statistics()
            self.stats_text.config(state=tk.NORMAL)
            self.stats_text.delete(1.0, tk.END)
            
            stats_str = f"Nodes: {stats.get('node_count', 'N/A')}\n"
            stats_str += f"Links: {stats.get('link_count', 'N/A')}\n"
            
            if self.simulation_run:
                stats_str += "\nSimulation: ✓ Run\n"
            else:
                stats_str += "\nSimulation: Not run\n"
            
            self.stats_text.insert(1.0, stats_str)
            self.stats_text.config(state=tk.DISABLED)
        except Exception as e:
            pass  # Silently fail if stats not available
    
    def update_plot(self):
        """Update the network plot based on selected options."""
        if not self.epanet.is_loaded():
            return
        
        try:
            # Clear everything including legends and colorbars
            self.ax.clear()
            
            # Remove all colorbars and other axes from the figure safely
            # Also remove any colorbars that might be attached
            axes_to_remove = []
            for item in list(self.figure.axes):  # Create a copy of the list
                if item != self.ax:
                    axes_to_remove.append(item)
            
            for ax_item in axes_to_remove:
                try:
                    # Remove colorbar if it exists
                    if hasattr(ax_item, 'colorbar'):
                        try:
                            ax_item.colorbar.remove()
                        except:
                            pass
                    ax_item.remove()
                except (ValueError, AttributeError):
                    pass  # Already removed or invalid
            
            # Restore original subplot parameters to prevent shrinking
            self.figure.subplots_adjust(left=0.05, right=0.92, top=0.95, bottom=0.05)
            
            # Remove previous annotation safely
            self.clear_annotation()
            
            # Build network graph for click detection
            if not self.use_epyt_native_var.get():
                self.network_graph, self.network_positions = self.epanet._build_networkx_graph()
                stats = self.epanet.get_statistics()
                
                # Store node info (index, ID mapping)
                node_names = stats.get('node_names', [])
                self.network_node_info = {}
                for idx, node_id in enumerate(node_names, start=1):
                    if node_id in self.network_positions:
                        self.network_node_info[node_id] = {
                            'index': idx,
                            'id': node_id,
                            'pos': self.network_positions[node_id]
                        }
                
                # Store link info
                link_names = stats.get('link_names', [])
                self.network_link_info = {}
                for idx, link_id in enumerate(link_names, start=1):
                    self.network_link_info[link_id] = {
                        'index': idx,
                        'id': link_id
                    }
            
            plot_type = self.plot_type_var.get()
            use_epyt = self.use_epyt_native_var.get()
            
            if plot_type == "topology":
                if use_epyt:
                    # EPyT native doesn't use custom axes - creates its own figure
                    self.epanet.plot_network_topology(ax=None, use_epyt_native=True,
                                                     nodesID=self.show_labels_var.get(),
                                                     linksID=self.show_labels_var.get())
                else:
                    self.epanet.plot_network_topology(ax=self.ax, use_epyt_native=False,
                                                     nodesID=self.show_labels_var.get(),
                                                     linksID=self.show_labels_var.get())
            elif plot_type == "elevation":
                if use_epyt:
                    self.epanet.plot_network_attributes(ax=None, attribute='elevation',
                                                       use_epyt_native=True)
                else:
                    self.epanet.plot_network_attributes(ax=self.ax, attribute='elevation',
                                                       use_epyt_native=False)
            elif plot_type == "pressure":
                if not self.simulation_run:
                    messagebox.showwarning("Warning", "Please run simulation first to view pressures.")
                    return
                if use_epyt:
                    # Don't pass pressure_text to epyt native - it's not a valid parameter
                    self.epanet.plot_network_attributes(ax=None, attribute='pressure',
                                                       use_epyt_native=True)
                else:
                    self.epanet.plot_network_attributes(ax=self.ax, attribute='pressure',
                                                       use_epyt_native=False,
                                                       pressure_text=self.show_labels_var.get())
            elif plot_type == "flow":
                if not self.simulation_run:
                    messagebox.showwarning("Warning", "Please run simulation first to view flows.")
                    return
                if use_epyt:
                    # Don't pass flow_text to epyt native
                    self.epanet.plot_network_attributes(ax=None, attribute='flow',
                                                       use_epyt_native=True)
                else:
                    self.epanet.plot_network_attributes(ax=self.ax, attribute='flow',
                                                       use_epyt_native=False,
                                                       flow_text=self.show_labels_var.get())
            elif plot_type == "quality":
                if not self.simulation_run:
                    messagebox.showwarning("Warning", "Please run simulation first to view quality.")
                    return
                try:
                    if use_epyt:
                        self.epanet.plot_network_attributes(ax=None, attribute='quality',
                                                          use_epyt_native=True)
                    else:
                        self.epanet.plot_network_attributes(ax=self.ax, attribute='quality',
                                                          use_epyt_native=False)
                except Exception:
                    messagebox.showerror("Error", "Quality data not available.")
                    return
            
            # Force restore fixed margins AFTER plotting to prevent canvas shrinking
            # This ensures layout stays consistent regardless of colorbars
            self.figure.subplots_adjust(left=0.05, right=0.92, top=0.95, bottom=0.05)
            self.canvas.draw()
        except Exception as e:
            messagebox.showerror("Error", f"Visualization Error: {e}")
    
    def on_plot_click(self, event):
        """Handle click events on the plot to show node/link information."""
        if not self.epanet.is_loaded():
            return
        
        # If clicking outside axes, always clear annotation
        if event.inaxes != self.ax:
            self.clear_annotation()
            self.canvas.draw()
            return
        
        # If clicking outside plot data area, clear annotation
        if event.xdata is None or event.ydata is None:
            self.clear_annotation()
            self.canvas.draw()
            return
        
        if self.use_epyt_native_var.get() or not self.network_positions:
            # Even with EPyT native, allow clearing by clicking
            self.clear_annotation()
            self.canvas.draw()
            return  # Click detection only works with NetworkX plots
        
        try:
            click_x, click_y = event.xdata, event.ydata
            
            # Clear previous annotation first
            self.clear_annotation()
            
            # Find closest node
            min_dist = float('inf')
            closest_node = None
            
            for node_id, info in self.network_node_info.items():
                node_x, node_y = info['pos']
                dist = ((click_x - node_x)**2 + (click_y - node_y)**2)**0.5
                if dist < min_dist:
                    min_dist = dist
                    closest_node = info
            
            # Check if click is close enough to a node (within reasonable distance)
            # Scale threshold based on plot size
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()
            threshold = max((xlim[1] - xlim[0]), (ylim[1] - ylim[0])) * 0.05  # 5% of plot size
            
            node_clicked = closest_node and min_dist < threshold
            
            # Check for links (edges) - always check, but prioritize nodes
            link_clicked = False
            closest_link = None
            closest_link_midpoint = None
            min_link_dist = float('inf')
            
            if self.network_graph:
                stats = self.epanet.get_statistics()
                link_names = stats.get('link_names', [])
                node_names = stats.get('node_names', [])
                
                for u, v in self.network_graph.edges():
                    if u in self.network_positions and v in self.network_positions:
                        x1, y1 = self.network_positions[u]
                        x2, y2 = self.network_positions[v]
                        
                        # Calculate distance from point to line segment
                        A = x2 - x1
                        B = y2 - y1
                        C = x1 - click_x
                        D = y1 - click_y
                        
                        dot = A * C + B * D
                        len_sq = A * A + B * B
                        
                        if len_sq != 0:
                            param = dot / len_sq
                            
                            if param < 0:
                                xx, yy = x1, y1
                            elif param > 1:
                                xx, yy = x2, y2
                            else:
                                xx, yy = x1 + param * A, y1 + param * B
                            
                            dist = ((click_x - xx)**2 + (click_y - yy)**2)**0.5
                            
                            if dist < min_link_dist:
                                min_link_dist = dist
                                # Get link info from graph edge data
                                edge_data = self.network_graph.get_edge_data(u, v, {})
                                link_id = edge_data.get('link_id', None)
                                
                                # If no link_id in edge data, try to find it by matching nodes
                                if not link_id or link_id not in self.network_link_info:
                                    # Try to find link that connects these two nodes
                                    for lid in link_names:
                                        try:
                                            link_idx = self.epanet.network.getLinkIndex(lid)
                                            nodes = self.epanet.network.getLinkNodesIndex(link_idx)
                                            if len(nodes) >= 2:
                                                start_node = node_names[nodes[0] - 1]
                                                end_node = node_names[nodes[1] - 1]
                                                if (start_node == u and end_node == v) or (start_node == v and end_node == u):
                                                    link_id = lid
                                                    break
                                        except Exception:
                                            continue
                                
                                if link_id and link_id in self.network_link_info:
                                    link_id_found = link_id
                                    closest_link = self.network_link_info[link_id]
                                    closest_link_midpoint = ((x1 + x2) / 2, (y1 + y2) / 2)
                
                # Check if click is close enough to a link (use same threshold)
                # Only show link if it's closer than node or node wasn't clicked
                if closest_link and min_link_dist < threshold:
                    if not node_clicked or min_link_dist < min_dist:
                        link_clicked = True
            
            # Show appropriate callout - prioritize nodes over links
            if node_clicked:
                # Show node information
                self.show_node_callout(closest_node, click_x, click_y)
            elif link_clicked:
                # Show link information
                self.show_link_callout(closest_link, closest_link_midpoint[0], closest_link_midpoint[1])
            else:
                # Click not close to any node or link - annotation already cleared above
                self.canvas.draw()
        
        except Exception as e:
            pass  # Silently handle errors
    
    def clear_annotation(self):
        """Safely remove annotation if it exists."""
        if self.annotation:
            try:
                self.annotation.remove()
            except (ValueError, AttributeError):
                pass  # Already removed or invalid
            finally:
                self.annotation = None
    
    def show_node_callout(self, node_info, x, y):
        """Show callout with node information."""
        # Remove previous annotation
        self.clear_annotation()
        
        # Get additional info
        stats = self.epanet.get_statistics()
        elevations = stats.get('node_elevations', {})
        elevation = elevations.get(node_info['id'], 'N/A') if isinstance(elevations, dict) else 'N/A'
        
        # Get pressure if simulation was run
        pressure = None
        if self.simulation_run:
            pressures = self.epanet.get_node_pressures()
            if pressures:
                pressure = pressures.get(node_info['id'], None)
        
        # Build info text
        info_text = f"Node Index: {node_info['index']}\n"
        info_text += f"Node ID: {node_info['id']}\n"
        info_text += f"Elevation: {elevation}"
        if pressure is not None:
            info_text += f"\nPressure: {pressure:.2f}"
        
        # Create annotation
        self.annotation = self.ax.annotate(
            info_text,
            xy=(x, y),
            xytext=(10, 10),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.8),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
            fontsize=9
        )
        
        # Update time series entry if it's empty or add to it (use node ID, not index)
        current_text = self.ts_indices_entry.get().strip()
        node_id = node_info['id']
        if not current_text:
            self.ts_indices_entry.delete(0, tk.END)
            self.ts_indices_entry.insert(0, node_id)
        elif self.ts_type_var.get() == 'pressure':
            # Only update if plotting pressure (nodes)
            items = [x.strip() for x in current_text.split(',')]
            if node_id not in items:
                items.append(node_id)
                self.ts_indices_entry.delete(0, tk.END)
                self.ts_indices_entry.insert(0, ','.join(items))
        
        self.canvas.draw()
    
    def show_link_callout(self, link_info, x, y):
        """Show callout with link information."""
        # Remove previous annotation
        self.clear_annotation()
        
        # Get flow if simulation was run
        flow = None
        if self.simulation_run:
            flows = self.epanet.get_link_flows()
            if flows:
                flow = flows.get(link_info['id'], None)
        
        # Build info text
        info_text = f"Link Index: {link_info['index']}\n"
        info_text += f"Link ID: {link_info['id']}"
        if flow is not None:
            info_text += f"\nFlow: {flow:.2f}"
        
        # Create annotation
        self.annotation = self.ax.annotate(
            info_text,
            xy=(x, y),
            xytext=(10, 10),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightblue", alpha=0.8),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
            fontsize=9
        )
        
        # Update time series entry if plotting velocity or flow (use link ID, not index)
        current_text = self.ts_indices_entry.get().strip()
        ts_type = self.ts_type_var.get()
        link_id = link_info['id']
        if ts_type in ['velocity', 'flow']:
            if not current_text:
                self.ts_indices_entry.delete(0, tk.END)
                self.ts_indices_entry.insert(0, link_id)
            else:
                items = [x.strip() for x in current_text.split(',')]
                if link_id not in items:
                    items.append(link_id)
                    self.ts_indices_entry.delete(0, tk.END)
                    self.ts_indices_entry.insert(0, ','.join(items))
        
        self.canvas.draw()
    
    def plot_time_series(self):
        """Plot time series data."""
        if not self.epanet.is_loaded():
            return
        
        if not self.simulation_run:
            messagebox.showwarning("Warning", "Please run simulation first to plot time series.")
            return
        
        try:
            # Parse indices or IDs (can be mixed)
            indices_str = self.ts_indices_entry.get().strip()
            if indices_str:
                # Parse as either IDs (strings) or indices (integers)
                items = []
                for x in indices_str.split(','):
                    x = x.strip()
                    try:
                        # Try to parse as integer (index)
                        items.append(int(x))
                    except ValueError:
                        # It's a string (ID)
                        items.append(x)
                indices = items
            else:
                indices = None
            
            plot_type = self.ts_type_var.get()
            
            # Create new window for time series
            ts_window = tk.Toplevel(self.root)
            ts_window.title(f"Time Series - {plot_type.capitalize()}")
            ts_window.geometry("800x600")
            
            fig, ax = plt.subplots(figsize=(8, 6))
            canvas = FigureCanvasTkAgg(fig, master=ts_window)
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
            # Determine if plotting nodes or links
            if plot_type == 'pressure':
                self.epanet.plot_time_series(ax=ax, node_indices=indices, 
                                           plot_type='pressure', time_unit='hours')
            elif plot_type == 'velocity':
                self.epanet.plot_time_series(ax=ax, link_indices=indices,
                                           plot_type='velocity', time_unit='hours')
            elif plot_type == 'flow':
                self.epanet.plot_time_series(ax=ax, link_indices=indices,
                                           plot_type='flow', time_unit='hours')
            
            canvas.draw()
        except Exception as e:
            messagebox.showerror("Error", f"Time series plotting failed: {e}")
    
    def show_network_info(self):
        """Show network information (node and link IDs) in a separate window."""
        if not self.epanet.is_loaded():
            messagebox.showwarning("Warning", "Please load a file first.")
            return
        
        try:
            stats = self.epanet.get_statistics()
            node_names = stats.get('node_names', [])
            link_names = stats.get('link_names', [])
            
            # Create info window
            info_window = tk.Toplevel(self.root)
            info_window.title("Network Information - Node and Link IDs")
            info_window.geometry("500x600")
            
            # Create notebook for tabs
            notebook = ttk.Notebook(info_window)
            notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Node IDs tab
            node_frame = tk.Frame(notebook)
            notebook.add(node_frame, text=f"Nodes ({len(node_names)})")
            
            node_scroll = tk.Scrollbar(node_frame)
            node_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            node_listbox = tk.Listbox(node_frame, yscrollcommand=node_scroll.set, width=50)
            node_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            node_scroll.config(command=node_listbox.yview)
            
            # Add nodes with index and ID
            for idx, node_id in enumerate(node_names, start=1):
                node_listbox.insert(tk.END, f"Index {idx}: {node_id}")
            
            # Add copy button for nodes
            def copy_node_ids():
                selected = node_listbox.curselection()
                if selected:
                    indices = [str(i + 1) for i in selected]
                    self.root.clipboard_clear()
                    self.root.clipboard_append(','.join(indices))
                    messagebox.showinfo("Copied", f"Copied indices: {','.join(indices)}")
                else:
                    # Copy all indices
                    all_indices = ','.join([str(i) for i in range(1, len(node_names) + 1)])
                    self.root.clipboard_clear()
                    self.root.clipboard_append(all_indices)
                    messagebox.showinfo("Copied", f"Copied all node indices: {all_indices}")
            
            node_copy_btn = tk.Button(node_frame, text="Copy Selected/All Indices", 
                                     command=copy_node_ids)
            node_copy_btn.pack(pady=5)
            
            # Link IDs tab
            link_frame = tk.Frame(notebook)
            notebook.add(link_frame, text=f"Links ({len(link_names)})")
            
            link_scroll = tk.Scrollbar(link_frame)
            link_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            link_listbox = tk.Listbox(link_frame, yscrollcommand=link_scroll.set, width=50)
            link_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            link_scroll.config(command=link_listbox.yview)
            
            # Add links with index and ID
            for idx, link_id in enumerate(link_names, start=1):
                link_listbox.insert(tk.END, f"Index {idx}: {link_id}")
            
            # Add copy button for links
            def copy_link_ids():
                selected = link_listbox.curselection()
                if selected:
                    indices = [str(i + 1) for i in selected]
                    self.root.clipboard_clear()
                    self.root.clipboard_append(','.join(indices))
                    messagebox.showinfo("Copied", f"Copied indices: {','.join(indices)}")
                else:
                    # Copy all indices
                    all_indices = ','.join([str(i) for i in range(1, len(link_names) + 1)])
                    self.root.clipboard_clear()
                    self.root.clipboard_append(all_indices)
                    messagebox.showinfo("Copied", f"Copied all link indices: {all_indices}")
            
            link_copy_btn = tk.Button(link_frame, text="Copy Selected/All Indices", 
                                     command=copy_link_ids)
            link_copy_btn.pack(pady=5)
            
            # Instructions
            instructions = tk.Label(info_window, 
                                   text="Select items and click Copy to get indices for time series plotting.\n"
                                        "If nothing selected, copies all indices.",
                                   font=("Arial", 9), justify=tk.LEFT)
            instructions.pack(pady=5)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to show network info: {e}")


# Run GUI
if __name__ == "__main__":
    root = tk.Tk()
    app = EPANETGUI(root)
    root.mainloop()
