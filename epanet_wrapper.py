"""
EPANET Wrapper Module

This module provides a shared interface for working with EPANET networks,
independent of the GUI framework. It can be used by Tkinter, Streamlit, Kivy, or any other GUI.

The visualization system uses NetworkX for proper graph representation, accounting for:
- 3D network topology (nodes with X, Y, elevation coordinates)
- Simulation results mapping (pressures, flows, velocities)
- Proper network graph visualization with connections
"""

from pathlib import Path
from typing import Optional, Dict, List, Tuple
from epyt import epanet
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np


class EpanetWrapper:
    """Wrapper class for EPANET operations using Pathlib."""
    
    def __init__(self, inp_file: Optional[Path] = None):
        """
        Initialize the EPANET wrapper.
        
        Args:
            inp_file: Path to the .inp file (optional, can be loaded later)
        """
        self.inp_file: Optional[Path] = None
        self.network = None
        self._statistics: Optional[Dict] = None
        self._computed_time_series: Optional[Dict] = None
        
        if inp_file:
            self.load_file(inp_file)
    
    def load_file(self, inp_file: Path) -> None:
        """
        Load an EPANET input file.
        
        Args:
            inp_file: Path to the .inp file
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file is not a .inp file
        """
        inp_path = Path(inp_file)
        
        if not inp_path.exists():
            raise FileNotFoundError(f"File not found: {inp_path}")
        
        if inp_path.suffix.lower() != '.inp':
            raise ValueError(f"File must be a .inp file, got: {inp_path.suffix}")
        
        self.inp_file = inp_path
        self.network = epanet(str(inp_path))
        # Load and store statistics
        self._update_statistics()
    
    def _update_statistics(self) -> None:
        """Update and store network statistics."""
        if self.network is None:
            return
        
        try:
            self._statistics = {
                'node_count': self.network.getNodeCount(),
                'link_count': self.network.getLinkCount(),
                'node_elevations': self.network.getNodeElevations(),
                'node_names': self.network.getNodeNameID(),
                'link_names': self.network.getLinkNameID(),
                'node_coordinates': self.network.getNodeCoordinates(),
            }
        except Exception:
            self._statistics = {}
    
    def get_statistics(self) -> Dict:
        """
        Get stored network statistics.
        
        Returns:
            Dictionary containing network statistics (node_count, link_count, elevations, etc.)
        """
        if self._statistics is None:
            self._update_statistics()
        return self._statistics.copy() if self._statistics else {}
    
    def run_simulation(self) -> None:
        """
        Run the hydraulic simulation.
        
        In epyt, getComputedTimeSeries() runs the simulation automatically.
        This method triggers the simulation and stores the results.
        
        Raises:
            RuntimeError: If no file is loaded or simulation fails
        """
        if self.network is None:
            raise RuntimeError("No EPANET file loaded. Please load a file first.")
        
        try:
            # In epyt, getComputedTimeSeries() runs the simulation automatically
            # This is the recommended way per EPyT examples
            self._computed_time_series = self.network.getComputedTimeSeries()
        except AttributeError:
            # Fallback: try other methods
            try:
                if hasattr(self.network, 'runCompleteSimulation'):
                    self.network.runCompleteSimulation()
                elif hasattr(self.network, 'solveCompleteHydraulics'):
                    self.network.solveCompleteHydraulics()
                elif hasattr(self.network, 'solveH'):
                    self.network.solveH()
                elif hasattr(self.network, 'runHydraulics'):
                    self.network.runHydraulics()
                else:
                    # Try to trigger simulation by accessing results
                    _ = self.network.getNodePressure()
            except Exception as e:
                available_methods = [m for m in dir(self.network) 
                                   if any(kw in m.lower() for kw in ['solve', 'run', 'hydraulic', 'complete', 'simulation', 'computed'])
                                   and not m.startswith('_')]
                raise RuntimeError(
                    f"Simulation method not found. "
                    f"Available simulation-related methods: {', '.join(available_methods) if available_methods else 'none found'}. "
                    f"Error: {e}"
                ) from e
        except Exception as e:
            raise RuntimeError(f"Simulation failed: {e}") from e
    
    def get_network(self):
        """
        Get the EPANET network object.
        
        Returns:
            The EPANET network object
            
        Raises:
            RuntimeError: If no file is loaded
        """
        if self.network is None:
            raise RuntimeError("No EPANET file loaded. Please load a file first.")
        
        return self.network
    
    def _build_networkx_graph(self) -> Tuple[nx.Graph, Dict]:
        """
        Build a NetworkX graph from the EPANET network with 3D coordinates.
        
        Returns:
            Tuple of (NetworkX graph, position dictionary with node coordinates)
            
        Raises:
            RuntimeError: If network data cannot be retrieved
        """
        if self.network is None:
            raise RuntimeError("No EPANET file loaded. Please load a file first.")
        
        G = nx.Graph()
        pos = {}
        
        try:
            # Get node coordinates (X, Y, elevation - 3D coordinates)
            node_coords = self.network.getNodeCoordinates()
            node_names = self.network.getNodeNameID()
            
            # Add nodes with coordinates
            for idx, node_id in enumerate(node_names, start=1):
                if node_id in node_coords:
                    x, y = node_coords[node_id][:2]  # X, Y coordinates
                    pos[node_id] = (x, y)
                    G.add_node(node_id)
                else:
                    # Fallback: use node index if coordinates not available
                    pos[node_id] = (idx * 10, idx * 10)
                    G.add_node(node_id)
            
            # Get link connections with proper mapping
            link_names = self.network.getLinkNameID()
            for link_id in link_names:
                try:
                    # Get start and end nodes for each link
                    link_index = self.network.getLinkIndex(link_id)
                    nodes = self.network.getLinkNodesIndex(link_index)
                    if len(nodes) >= 2:
                        start_node = node_names[nodes[0] - 1]  # epyt uses 1-based indexing
                        end_node = node_names[nodes[1] - 1]
                        # Store link_id in edge data for easy retrieval
                        G.add_edge(start_node, end_node, link_id=link_id)
                except Exception:
                    continue  # Skip links that can't be processed
            
        except Exception as e:
            raise RuntimeError(f"Failed to build network graph: {e}") from e
        
        return G, pos
    
    def _get_simulation_results(self) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Get simulation results for visualization (pressures, flows).
        
        Returns:
            Tuple of (node_pressures dict, link_flows dict) or (None, None) if simulation not run
        """
        if self.network is None:
            return None, None
        
        try:
            # Try to get results from computed time series first (more reliable)
            res = self.get_computed_time_series()
            node_pressures = {}
            link_flows = {}
            
            if res is not None:
                # Get node names and link names
                node_names = self.network.getNodeNameID()
                link_names = self.network.getLinkNameID()
                
                # Extract pressures from time series (use first time step or average)
                if hasattr(res, 'Pressure') and res.Pressure is not None:
                    # Use average across all time steps, or first time step if only one
                    if len(res.Pressure.shape) > 1:
                        pressures_avg = np.mean(res.Pressure, axis=0)
                    else:
                        pressures_avg = res.Pressure
                    
                    for idx, node_id in enumerate(node_names):
                        if idx < len(pressures_avg):
                            node_pressures[node_id] = float(pressures_avg[idx])
                
                # Extract flows from time series
                if hasattr(res, 'Flow') and res.Flow is not None:
                    if len(res.Flow.shape) > 1:
                        flows_avg = np.mean(res.Flow, axis=0)
                    else:
                        flows_avg = res.Flow
                    
                    for idx, link_id in enumerate(link_names):
                        if idx < len(flows_avg):
                            link_flows[link_id] = float(flows_avg[idx])
                
                return node_pressures if node_pressures else None, link_flows if link_flows else None
            
            # Fallback: Try direct methods
            node_names = self.network.getNodeNameID()
            try:
                pressures = self.network.getNodePressure()
                if pressures is not None:
                    for idx, node_id in enumerate(node_names):
                        if idx < len(pressures):
                            pressure_values = pressures[idx] if isinstance(pressures[idx], (list, np.ndarray)) else [pressures[idx]]
                            node_pressures[node_id] = np.mean(pressure_values) if len(pressure_values) > 0 else 0.0
            except Exception:
                pass
            
            link_names = self.network.getLinkNameID()
            try:
                flows = self.network.getLinkFlows()
                if flows is not None:
                    for idx, link_id in enumerate(link_names):
                        if idx < len(flows):
                            flow_values = flows[idx] if isinstance(flows[idx], (list, np.ndarray)) else [flows[idx]]
                            link_flows[link_id] = np.mean(flow_values) if len(flow_values) > 0 else 0.0
            except Exception:
                pass
            
            return node_pressures if node_pressures else None, link_flows if link_flows else None
            
        except Exception as e:
            return None, None
    
    def plot_network(self, ax=None, show_pressures: bool = False, show_flows: bool = False):
        """
        Plot the network visualization using NetworkX.
        
        This method properly handles:
        - 3D network topology (uses X, Y coordinates from EPANET)
        - Simulation results visualization (pressures, flows)
        - Proper graph representation with node connections
        
        Args:
            ax: Matplotlib axes object (optional). If provided, the plot will be drawn on this axes.
            show_pressures: If True, color nodes by pressure values (requires simulation to be run)
            show_flows: If True, color edges by flow values (requires simulation to be run)
            
        Raises:
            RuntimeError: If no file is loaded or plotting fails
        """
        if self.network is None:
            raise RuntimeError("No EPANET file loaded. Please load a file first.")
        
        try:
            # Build NetworkX graph with 3D coordinates
            G, pos = self._build_networkx_graph()
            
            if ax is not None:
                ax.clear()
                
                # Get simulation results if requested
                node_pressures, link_flows = None, None
                if show_pressures or show_flows:
                    node_pressures, link_flows = self._get_simulation_results()
                
                # Prepare node colors based on pressures
                node_colors = None
                if show_pressures and node_pressures:
                    node_colors = [node_pressures.get(node, 0.0) for node in G.nodes()]
                    if node_colors and all(c == 0.0 for c in node_colors):
                        node_colors = 'lightblue'  # Fallback if no pressure data
                else:
                    node_colors = 'lightblue'
                
                # Prepare edge colors based on flows
                edge_colors = None
                if show_flows and link_flows:
                    edge_colors = []
                    for u, v, data in G.edges(data=True):
                        link_id = data.get('link_id', '')
                        edge_colors.append(link_flows.get(link_id, 0.0))
                    if edge_colors and all(c == 0.0 for c in edge_colors):
                        edge_colors = 'gray'  # Fallback if no flow data
                else:
                    edge_colors = 'gray'
                
                # Draw the network using NetworkX
                # Use node coordinates for positioning (preserves 3D spatial layout)
                nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                                      node_size=300, alpha=0.9, cmap=plt.cm.viridis if show_pressures and isinstance(node_colors, list) else None)
                
                nx.draw_networkx_edges(G, pos, ax=ax, edge_color=edge_colors,
                                      width=2, alpha=0.6, 
                                      edge_cmap=plt.cm.plasma if show_flows and isinstance(edge_colors, list) else None)
                
                # Add node labels
                nx.draw_networkx_labels(G, pos, ax=ax, font_size=8, font_weight='bold')
                
                ax.set_aspect('equal', adjustable='box')
                ax.axis('off')
                ax.set_title('EPANET Network' + 
                           (' (Pressures)' if show_pressures else '') +
                           (' (Flows)' if show_flows else ''))
                
                # Add colorbar if showing simulation results
                if show_pressures and isinstance(node_colors, list) and node_colors:
                    sm = plt.cm.ScalarMappable(cmap=plt.cm.viridis, 
                                             norm=plt.Normalize(vmin=min(node_colors), vmax=max(node_colors)))
                    sm.set_array([])
                    plt.colorbar(sm, ax=ax, label='Pressure')
                
            else:
                # No axes provided, create a new figure
                fig, ax = plt.subplots(figsize=(10, 8))
                self.plot_network(ax=ax, show_pressures=show_pressures, show_flows=show_flows)
                plt.show()
                
        except Exception as e:
            raise RuntimeError(f"Plotting failed: {e}") from e
    
    def get_file_name(self) -> Optional[str]:
        """
        Get the name of the loaded file.
        
        Returns:
            The file name (without path) or None if no file is loaded
        """
        if self.inp_file is None:
            return None
        return self.inp_file.name
    
    def get_file_path(self) -> Optional[Path]:
        """
        Get the full path of the loaded file.
        
        Returns:
            The Path object or None if no file is loaded
        """
        return self.inp_file
    
    def is_loaded(self) -> bool:
        """
        Check if a file is currently loaded.
        
        Returns:
            True if a file is loaded, False otherwise
        """
        return self.network is not None
    
    def get_node_pressures(self) -> Optional[Dict[str, float]]:
        """
        Get node pressures from simulation results.
        
        Returns:
            Dictionary mapping node IDs to average pressure values, or None if simulation not run
        """
        node_pressures, _ = self._get_simulation_results()
        return node_pressures
    
    def get_link_flows(self) -> Optional[Dict[str, float]]:
        """
        Get link flows from simulation results.
        
        Returns:
            Dictionary mapping link IDs to average flow values, or None if simulation not run
        """
        _, link_flows = self._get_simulation_results()
        return link_flows
    
    def get_computed_time_series(self) -> Optional[Dict]:
        """
        Get computed time series results from simulation.
        
        Returns:
            Dictionary with Time, Pressure, Velocity, Flow arrays, or None if simulation not run
        """
        if self._computed_time_series is None:
            try:
                self._computed_time_series = self.network.getComputedTimeSeries()
            except Exception:
                return None
        return self._computed_time_series
    
    def plot_network_attributes(self, ax=None, attribute: str = 'elevation', 
                                use_epyt_native: bool = False, **kwargs):
        """
        Plot network with different attributes (elevation, pressure, flow, quality).
        
        Based on EPyT examples: https://github.com/KIOS-Research/EPyT/blob/main/epyt/examples/EX5_Plot_values_parameters.py
        
        Args:
            ax: Matplotlib axes object (optional)
            attribute: Attribute to plot ('elevation', 'pressure', 'flow', 'quality')
            use_epyt_native: If True, use epyt's native plotting; if False, use NetworkX
            **kwargs: Additional arguments for epyt.plot() when use_epyt_native=True
                      (e.g., pressure_text=True, flow_text=True, title='...')
        
        Raises:
            RuntimeError: If no file is loaded or plotting fails
        """
        if self.network is None:
            raise RuntimeError("No EPANET file loaded. Please load a file first.")
        
        if use_epyt_native:
            # Use epyt's native plotting (as in EX5 example)
            # Note: epyt.plot() creates its own figure, so we can't use custom axes
            try:
                # Filter kwargs - epyt.plot() has specific parameter names
                # Remove any kwargs that might cause issues
                plot_kwargs = {}
                valid_epyt_params = ['nodesID', 'linksID', 'nodesindex', 'linksindex', 
                                    'highlightlink', 'highlightnode', 'point', 'line', 
                                    'legend', 'title', 'colorbar']
                
                for key, value in kwargs.items():
                    # Only pass valid epyt parameters
                    if key in valid_epyt_params:
                        plot_kwargs[key] = value
                    # Skip boolean values that aren't in valid list (like pressure_text, flow_text)
                    elif not isinstance(value, bool):
                        # Allow non-boolean values that might be valid
                        if key not in ['pressure_text', 'flow_text', 'hour']:
                            plot_kwargs[key] = value
                
                if attribute == 'elevation':
                    elevations = self.network.getNodeElevations()
                    self.network.plot(elevation=True, colorbar='Oranges', **plot_kwargs)
                elif attribute == 'pressure':
                    # Need simulation results
                    res = self.get_computed_time_series()
                    if res is None:
                        raise RuntimeError("Simulation must be run first to plot pressures")
                    # Plot pressure at first time step by default
                    hour = kwargs.get('hour', 0)
                    if hour >= len(res.Pressure):
                        hour = 0
                    # Don't pass pressure_text as it might cause issues - epyt handles it differently
                    self.network.plot(pressure=res.Pressure[hour, :], **plot_kwargs)
                elif attribute == 'flow':
                    res = self.get_computed_time_series()
                    if res is None:
                        raise RuntimeError("Simulation must be run first to plot flows")
                    hour = kwargs.get('hour', 0)
                    if hour >= len(res.Flow):
                        hour = 0
                    self.network.plot(flow=res.Flow[hour, :], **plot_kwargs)
                elif attribute == 'quality':
                    res = self.get_computed_time_series()
                    if res is None:
                        raise RuntimeError("Simulation must be run first to plot quality")
                    hour = kwargs.get('hour', 0)
                    if hasattr(res, 'Quality') and hour < len(res.Quality):
                        self.network.plot(quality=res.Quality[hour, :], **plot_kwargs)
                    else:
                        raise RuntimeError("Quality data not available")
                else:
                    raise ValueError(f"Unknown attribute: {attribute}. Use 'elevation', 'pressure', 'flow', or 'quality'")
            except Exception as e:
                raise RuntimeError(f"Plotting failed: {e}") from e
        else:
            # Use NetworkX plotting (our custom implementation)
            if attribute == 'elevation':
                self.plot_network(ax=ax, show_pressures=False, show_flows=False)
                # Override with elevation colors
                stats = self.get_statistics()
                if 'node_elevations' in stats and ax:
                    G, pos = self._build_networkx_graph()
                    elevations = stats['node_elevations']
                    node_colors = [elevations.get(node, 0.0) if isinstance(elevations, dict) 
                                 else elevations[i] if i < len(elevations) else 0.0
                                 for i, node in enumerate(G.nodes())]
                    ax.clear()
                    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                                          node_size=300, alpha=0.9, cmap=plt.cm.Oranges)
                    nx.draw_networkx_edges(G, pos, ax=ax, edge_color='gray', width=2, alpha=0.6)
                    nx.draw_networkx_labels(G, pos, ax=ax, font_size=8, font_weight='bold')
                    ax.set_aspect('equal', adjustable='box')
                    ax.axis('off')
                    ax.set_title('EPANET Network - Elevations')
                    if isinstance(node_colors, list) and node_colors:
                        sm = plt.cm.ScalarMappable(cmap=plt.cm.Oranges,
                                                 norm=plt.Normalize(vmin=min(node_colors), vmax=max(node_colors)))
                        sm.set_array([])
                        plt.colorbar(sm, ax=ax, label='Elevation')
            elif attribute == 'pressure':
                self.plot_network(ax=ax, show_pressures=True, show_flows=False)
            elif attribute == 'flow':
                self.plot_network(ax=ax, show_pressures=False, show_flows=True)
            else:
                raise ValueError(f"Unknown attribute: {attribute}. Use 'elevation', 'pressure', or 'flow'")
    
    def plot_time_series(self, ax=None, node_indices: Optional[List] = None,
                        link_indices: Optional[List] = None,
                        plot_type: str = 'pressure', time_unit: str = 'hours'):
        """
        Plot time series for node pressures, velocities, or flows.
        
        Based on EPyT examples: https://github.com/KIOS-Research/EPyT/blob/main/epyt/examples/EX4_Plot_time_series.py
        
        Args:
            ax: Matplotlib axes object (optional). If None, creates new figure
            node_indices: List of node indices (int) or node IDs (str) to plot (1-based indices, as in EPANET)
            link_indices: List of link indices (int) or link IDs (str) to plot (1-based indices, as in EPANET)
            plot_type: Type of plot ('pressure', 'velocity', 'flow')
            time_unit: Time unit for x-axis ('hours' or 'seconds')
        
        Raises:
            RuntimeError: If no file is loaded, simulation not run, or plotting fails
        """
        if self.network is None:
            raise RuntimeError("No EPANET file loaded. Please load a file first.")
        
        # Get computed time series (runs simulation if needed)
        res = self.get_computed_time_series()
        if res is None:
            raise RuntimeError("Simulation must be run first. Call run_simulation() before plotting time series.")
        
        try:
            # Convert time from seconds to requested unit
            if time_unit == 'hours':
                time_data = res.Time / 3600
                xlabel = 'Time (hrs)'
            else:
                time_data = res.Time
                xlabel = 'Time (sec)'
            
            # Create figure if no axes provided
            if ax is None:
                fig, ax = plt.subplots(figsize=(10, 6))
            
            if plot_type == 'pressure':
                if node_indices is None:
                    # Plot all nodes
                    node_indices = list(range(1, self.get_statistics()['node_count'] + 1))
                
                # Convert node IDs to indices if needed
                node_indices_to_plot = []
                node_names = self.network.getNodeNameID()
                
                for item in node_indices:
                    if isinstance(item, str):
                        # It's a node ID, find its index
                        try:
                            idx = node_names.index(item) + 1  # EPANET uses 1-based indexing
                            node_indices_to_plot.append(idx)
                        except ValueError:
                            raise ValueError(f"Node ID '{item}' not found in network")
                    else:
                        # It's already an index
                        node_indices_to_plot.append(int(item))
                
                for node_idx in node_indices_to_plot:
                    if node_idx <= len(res.Pressure[0]):
                        node_name = self.network.getNodeNameID(node_idx)
                        ax.plot(time_data, res.Pressure[:, node_idx - 1],
                               label=f'Node {node_name}', marker=None)
                ax.set_ylabel(f'Pressure ({self.network.units.NodePressureUnits})')
                ax.set_title('Node Pressures Over Time')
            
            elif plot_type == 'velocity':
                if link_indices is None:
                    # Plot all links
                    link_indices = list(range(1, self.get_statistics()['link_count'] + 1))
                
                # Convert link IDs to indices if needed
                link_indices_to_plot = []
                link_names = self.network.getLinkNameID()
                
                for item in link_indices:
                    if isinstance(item, str):
                        # It's a link ID, find its index
                        try:
                            idx = link_names.index(item) + 1  # EPANET uses 1-based indexing
                            link_indices_to_plot.append(idx)
                        except ValueError:
                            raise ValueError(f"Link ID '{item}' not found in network")
                    else:
                        # It's already an index
                        link_indices_to_plot.append(int(item))
                
                for link_idx in link_indices_to_plot:
                    if link_idx <= len(res.Velocity[0]):
                        link_name = self.network.getLinkNameID(link_idx)
                        ax.plot(time_data, res.Velocity[:, link_idx - 1],
                               label=f'Link {link_name}', marker=None)
                ax.set_ylabel(f'Velocity ({self.network.units.LinkVelocityUnits})')
                ax.set_title('Link Velocities Over Time')
            
            elif plot_type == 'flow':
                if link_indices is None:
                    # Plot all links
                    link_indices = list(range(1, self.get_statistics()['link_count'] + 1))
                
                # Convert link IDs to indices if needed
                link_indices_to_plot = []
                link_names = self.network.getLinkNameID()
                
                for item in link_indices:
                    if isinstance(item, str):
                        # It's a link ID, find its index
                        try:
                            idx = link_names.index(item) + 1  # EPANET uses 1-based indexing
                            link_indices_to_plot.append(idx)
                        except ValueError:
                            raise ValueError(f"Link ID '{item}' not found in network")
                    else:
                        # It's already an index
                        link_indices_to_plot.append(int(item))
                
                for link_idx in link_indices_to_plot:
                    if link_idx <= len(res.Flow[0]):
                        link_name = self.network.getLinkNameID(link_idx)
                        ax.plot(time_data, res.Flow[:, link_idx - 1],
                               label=f'Link {link_name}', marker=None)
                ax.set_ylabel(f'Flow ({self.network.units.LinkFlowUnits})')
                ax.set_title('Link Flows Over Time')
            
            else:
                raise ValueError(f"Unknown plot_type: {plot_type}. Use 'pressure', 'velocity', or 'flow'")
            
            ax.set_xlabel(xlabel)
            ax.legend()
            ax.grid(True, alpha=0.3)
                
        except Exception as e:
            raise RuntimeError(f"Time series plotting failed: {e}") from e
    
    def plot_network_topology(self, ax=None, use_epyt_native: bool = False, **kwargs):
        """
        Plot network topology with various options.
        
        Based on EPyT examples: https://github.com/KIOS-Research/EPyT/blob/main/epyt/examples/EX1_Plot_network_topology.py
        
        Args:
            ax: Matplotlib axes object (optional)
            use_epyt_native: If True, use epyt's native plotting; if False, use NetworkX
            **kwargs: Additional arguments for epyt.plot() when use_epyt_native=True
                     (e.g., nodesID=True, linksID=True, highlightnode=['10'], etc.)
        
        Raises:
            RuntimeError: If no file is loaded or plotting fails
        """
        if self.network is None:
            raise RuntimeError("No EPANET file loaded. Please load a file first.")
        
        if use_epyt_native:
            # Use epyt's native plotting
            # Filter out problematic kwargs - only pass valid epyt.plot() parameters
            try:
                plot_kwargs = {}
                valid_epyt_params = ['nodesID', 'linksID', 'nodesindex', 'linksindex', 
                                    'highlightlink', 'highlightnode', 'point', 'line', 
                                    'legend', 'title']
                
                for key, value in kwargs.items():
                    # Only pass valid epyt parameters
                    if key in valid_epyt_params:
                        plot_kwargs[key] = value
                    # Skip boolean values that aren't in valid list
                    elif not isinstance(value, bool):
                        plot_kwargs[key] = value
                
                self.network.plot(**plot_kwargs)
            except Exception as e:
                raise RuntimeError(f"Plotting failed: {e}") from e
        else:
            # Use our NetworkX implementation (preferred for better control)
            self.plot_network(ax=ax, show_pressures=False, show_flows=False)
    
    def get_node_elevations(self) -> Optional[Dict[str, float]]:
        """
        Get node elevations.
        
        Returns:
            Dictionary mapping node IDs to elevation values, or None if not available
        """
        stats = self.get_statistics()
        elevations = stats.get('node_elevations')
        if elevations is None:
            return None
        
        # Convert to dict if it's a list/array
        if isinstance(elevations, (list, np.ndarray)):
            node_names = stats.get('node_names', [])
            return {name: float(elev) for name, elev in zip(node_names, elevations)}
        return elevations
    
    def get_node_attribute(self, attribute: str) -> Optional[Dict]:
        """
        Get a specific node attribute.
        
        Args:
            attribute: Attribute name ('elevation', 'pressure', 'quality', etc.)
        
        Returns:
            Dictionary mapping node IDs to attribute values, or None if not available
        """
        if self.network is None:
            return None
        
        try:
            if attribute == 'elevation':
                return self.get_node_elevations()
            elif attribute == 'pressure':
                return self.get_node_pressures()
            else:
                # Try to get attribute using getNode* methods
                method_name = f'getNode{attribute.capitalize()}'
                if hasattr(self.network, method_name):
                    method = getattr(self.network, method_name)
                    values = method()
                    node_names = self.network.getNodeNameID()
                    if isinstance(values, (list, np.ndarray)):
                        return {name: float(val) for name, val in zip(node_names, values)}
                    return values
        except Exception:
            pass
        return None
    
    def close(self) -> None:
        """Close the network and clean up resources."""
        if self.network is not None:
            try:
                self.network.unload()
            except Exception:
                pass  # Ignore errors during cleanup
            finally:
                self.network = None
                self.inp_file = None
                self._statistics = None
                self._computed_time_series = None

