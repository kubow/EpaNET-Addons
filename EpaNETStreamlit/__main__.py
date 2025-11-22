"""
Streamlit GUI for EPANET

This module provides a Streamlit-based GUI for EPANET network analysis.
Run with: streamlit run EpaNETStreamlit/__main__.py
"""

import streamlit as st
from pathlib import Path
import sys
import matplotlib.pyplot as plt

# Add parent directory to path to import epanet_wrapper
sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_wrapper import EpanetWrapper

st.set_page_config(page_title="EPANET Streamlit GUI", layout="wide")

st.title("EPANET Network Analysis")

# Initialize session state
if 'epanet' not in st.session_state:
    st.session_state.epanet = EpanetWrapper()
    st.session_state.simulation_run = False
    st.session_state.file_loaded = False

# Sidebar for controls
with st.sidebar:
    # Toolbox (expandable)
    with st.expander("Toolbox", expanded=True):
        # File uploader
        uploaded_file = st.file_uploader("Upload EPANET .inp file", type=['inp'], key="file_upload")
        
        if uploaded_file is not None:
            # Save uploaded file temporarily
            temp_path = Path("/tmp") / uploaded_file.name
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            try:
                st.session_state.epanet.load_file(temp_path)
                st.session_state.file_loaded = True
                st.session_state.simulation_run = False
                st.success(f"✓ Loaded: {uploaded_file.name}")
            except Exception as e:
                st.error(f"Error loading file: {e}")
                st.session_state.file_loaded = False
        
        # Run simulation button
        if st.button("Run Simulation", disabled=not st.session_state.file_loaded, use_container_width=True):
            if st.session_state.file_loaded:
                try:
                    with st.spinner("Running simulation..."):
                        st.session_state.epanet.run_simulation()
                        st.session_state.simulation_run = True
                    st.success("✓ Simulation completed!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Simulation error: {e}")
        
        # Show Links button
        if st.button("Show Links", disabled=not st.session_state.file_loaded, use_container_width=True):
            if st.session_state.file_loaded:
                st.session_state.show_links = True
        
        # Options
        st.checkbox("Show Labels", value=False, disabled=not st.session_state.file_loaded, key="show_labels")
        st.checkbox("EPyT Native Plot", value=False, disabled=not st.session_state.file_loaded, key="use_epyt")
    
    # Network Statistics
    if st.session_state.file_loaded:
        with st.expander("Network Stats", expanded=True):
            try:
                stats = st.session_state.epanet.get_statistics()
                st.write(f"**Nodes:** {stats.get('node_count', 'N/A')}")
                st.write(f"**Links:** {stats.get('link_count', 'N/A')}")
                if st.session_state.simulation_run:
                    st.write("**Simulation:** ✓ Run")
                else:
                    st.write("**Simulation:** Not run")
            except Exception:
                pass
    
    # Visualization (expandable)
    if st.session_state.file_loaded:
        with st.expander("Visualization", expanded=True):
            # Plot type selection
            plot_type = st.radio(
                "Plot Type",
                ["Topology", "Elevation", "Pressure", "Flow", "Quality"],
                key="plot_type"
            )
            
            plot_type_lower = plot_type.lower()
            
            # Check if simulation is needed
            if plot_type_lower in ['pressure', 'flow', 'quality'] and not st.session_state.simulation_run:
                st.warning("⚠️ Run simulation first")
            else:
                # Update plot button
                if st.button("Update Plot", use_container_width=True, key="update_plot"):
                    st.session_state.update_plot_trigger = True
                    st.rerun()
    
    # Time Series (expandable)
    if st.session_state.file_loaded:
        with st.expander("Time Series", expanded=False):
            ts_type = st.radio(
                "Plot Type",
                ["Pressure", "Velocity", "Flow"],
                key="ts_type"
            )
            
            ts_indices = st.text_input(
                "Node/Link IDs or Indices",
                value="J1,J3,J5",
                help="Comma-separated (e.g., J1,J3 or 1,3)",
                key="ts_indices"
            )
            
            if st.button("Plot Time Series", disabled=not st.session_state.simulation_run, use_container_width=True, key="plot_ts"):
                if st.session_state.simulation_run:
                    st.session_state.plot_ts_trigger = True
                    st.rerun()
                else:
                    st.warning("Please run simulation first")

# Main content area
if st.session_state.file_loaded:
    # Get options from session state
    show_labels = st.session_state.get('show_labels', False)
    use_epyt_native = st.session_state.get('use_epyt', False)
    
    # Handle plot updates
    if st.session_state.get('update_plot_trigger', False):
        st.session_state.update_plot_trigger = False
        try:
            plot_type = st.session_state.get('plot_type', 'Topology')
            plot_type_lower = plot_type.lower()
            
            fig, ax = plt.subplots(figsize=(12, 8))
            
            if plot_type_lower == "topology":
                st.session_state.epanet.plot_network_topology(
                    ax=ax, 
                    use_epyt_native=use_epyt_native,
                    nodesID=show_labels,
                    linksID=show_labels
                )
            elif plot_type_lower == "elevation":
                st.session_state.epanet.plot_network_attributes(
                    ax=ax, 
                    attribute='elevation',
                    use_epyt_native=use_epyt_native
                )
            elif plot_type_lower == "pressure":
                st.session_state.epanet.plot_network_attributes(
                    ax=ax, 
                    attribute='pressure',
                    use_epyt_native=use_epyt_native,
                    pressure_text=show_labels
                )
            elif plot_type_lower == "flow":
                st.session_state.epanet.plot_network_attributes(
                    ax=ax, 
                    attribute='flow',
                    use_epyt_native=use_epyt_native,
                    flow_text=show_labels
                )
            elif plot_type_lower == "quality":
                st.session_state.epanet.plot_network_attributes(
                    ax=ax, 
                    attribute='quality',
                    use_epyt_native=use_epyt_native
                )
            
            st.pyplot(fig)
            plt.close(fig)
        except Exception as e:
            st.error(f"Visualization error: {e}")
    
    # Handle time series plotting
    if st.session_state.get('plot_ts_trigger', False):
        st.session_state.plot_ts_trigger = False
        try:
            ts_type = st.session_state.get('ts_type', 'Pressure')
            ts_indices = st.session_state.get('ts_indices', 'J1,J3,J5')
            
            # Parse indices
            if ts_indices.strip():
                items = []
                for x in ts_indices.split(','):
                    x = x.strip()
                    try:
                        items.append(int(x))
                    except ValueError:
                        items.append(x)
                indices = items
            else:
                indices = None
            
            fig, ax = plt.subplots(figsize=(10, 6))
            
            if ts_type.lower() == 'pressure':
                st.session_state.epanet.plot_time_series(
                    ax=ax, 
                    node_indices=indices,
                    plot_type='pressure', 
                    time_unit='hours'
                )
            elif ts_type.lower() == 'velocity':
                st.session_state.epanet.plot_time_series(
                    ax=ax, 
                    link_indices=indices,
                    plot_type='velocity', 
                    time_unit='hours'
                )
            elif ts_type.lower() == 'flow':
                st.session_state.epanet.plot_time_series(
                    ax=ax, 
                    link_indices=indices,
                    plot_type='flow', 
                    time_unit='hours'
                )
            
            st.pyplot(fig)
            plt.close(fig)
        except Exception as e:
            st.error(f"Time series plotting failed: {e}")
    
    # Network Info expander
    with st.expander("Network Information - Node and Link IDs"):
        try:
            stats = st.session_state.epanet.get_statistics()
            node_names = stats.get('node_names', [])
            link_names = stats.get('link_names', [])
            
            tab1, tab2 = st.tabs([f"Nodes ({len(node_names)})", f"Links ({len(link_names)})"])
            
            with tab1:
                # Display nodes with index and ID
                node_data = [f"Index {idx}: {node_id}" for idx, node_id in enumerate(node_names, start=1)]
                selected_nodes = st.multiselect(
                    "Select nodes to copy indices",
                    node_data,
                    key="node_select"
                )
                if selected_nodes:
                    # Extract indices
                    indices = []
                    for item in selected_nodes:
                        idx = item.split(':')[0].replace('Index ', '')
                        indices.append(idx)
                    indices_str = ','.join(indices)
                    st.code(indices_str, language=None)
                    if st.button("Copy Node Indices", key="copy_nodes"):
                        st.code(indices_str)
                else:
                    # Show all
                    all_indices = ','.join([str(i) for i in range(1, len(node_names) + 1)])
                    st.code(f"All node indices: {all_indices}", language=None)
            
            with tab2:
                # Display links with index and ID
                link_data = [f"Index {idx}: {link_id}" for idx, link_id in enumerate(link_names, start=1)]
                selected_links = st.multiselect(
                    "Select links to copy indices",
                    link_data,
                    key="link_select"
                )
                if selected_links:
                    # Extract indices
                    indices = []
                    for item in selected_links:
                        idx = item.split(':')[0].replace('Index ', '')
                        indices.append(idx)
                    indices_str = ','.join(indices)
                    st.code(indices_str, language=None)
                    if st.button("Copy Link Indices", key="copy_links"):
                        st.code(indices_str)
                else:
                    # Show all
                    all_indices = ','.join([str(i) for i in range(1, len(link_names) + 1)])
                    st.code(f"All link indices: {all_indices}", language=None)
        except Exception as e:
            st.error(f"Error showing network info: {e}")
    
    # Auto-display network on load or show current plot
    if not st.session_state.get('update_plot_trigger', False) and not st.session_state.get('plot_ts_trigger', False):
        if 'auto_plot' not in st.session_state:
            st.session_state.auto_plot = True
        try:
            fig, ax = plt.subplots(figsize=(12, 8))
            st.session_state.epanet.plot_network_topology(ax=ax, use_epyt_native=False)
            st.pyplot(fig)
            plt.close(fig)
        except Exception:
            pass

else:
    st.info("👈 Please upload an EPANET .inp file from the sidebar to get started.")
    
    # Show sample files if available
    samples_dir = Path(__file__).parent.parent / "samples"
    if samples_dir.exists():
        sample_files = list(samples_dir.glob("*.inp"))
        if sample_files:
            st.subheader("Sample Files Available")
            for sample_file in sample_files:
                if st.button(f"Load {sample_file.name}", key=f"load_{sample_file.name}"):
                    try:
                        st.session_state.epanet.load_file(sample_file)
                        st.session_state.file_loaded = True
                        st.session_state.simulation_run = False
                        st.success(f"✓ Loaded: {sample_file.name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error loading file: {e}")
