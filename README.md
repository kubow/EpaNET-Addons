# EPANET Multi-GUI Framework

A comprehensive Python framework for EPANET network analysis with multiple GUI implementations. This project provides a unified interface to EPANET functionality through a shared core wrapper, enabling easy development and deployment across different GUI frameworks.

## 🎯 Features

### Core Functionality
- **Network Loading**: Load EPANET `.inp` files with robust error handling
- **Simulation**: Run hydraulic and water quality simulations
- **Statistics**: Retrieve network metadata (node/link counts, elevations, coordinates, names)
- **Network Visualization**: 
  - Network topology plotting (NetworkX-based or EPyT native)
  - Attribute mapping (elevation, pressure, flow, quality)
  - Interactive node/link callouts (Tkinter)
  - Customizable labels and styling
- **Time Series Analysis**: Plot pressure, velocity, and flow over time for specific nodes/links
- **Node/Link Information**: Browse and select network components by ID or index

### GUI Implementations

#### ✅ Implemented
- **Tkinter** (`EpaNETTk`) - Desktop GUI with interactive plotting, click callouts, and comprehensive controls
- **Streamlit** (`EpaNETStreamlit`) - Web-based dashboard with expandable sidebar sections

#### 🚧 Placeholder Implementations (Ready for Development)
- **CustomTkinter** (`EpaNETCustomTkinter`) - Modern Tkinter with custom styling
- **PyQt/PySide** (`EpaNETPyQt`) - Qt-based cross-platform desktop application
- **wxPython** (`EpaNETwxPython`) - Native look and feel desktop GUI
- **Kivy** (`EpaNETKivy`) - Modern touch-friendly GUI framework
- **Flask** (`EpaNETFlask`) - Full-featured web application
- **Flet** (`EpaNETFlet`) - Flutter-based cross-platform GUI


## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip

### Setup

1. **Clone the repository** (or navigate to the project directory)

2. **Create a virtual environment** (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies for your chosen GUI**:

```bash
# For Tkinter GUI
pip install -r requirements/tkinter.in

# For Streamlit GUI
pip install -r requirements/streamlit.in

# For other GUIs, install their respective requirements files
```

### Base Dependencies
All GUIs require the base dependencies:
- `epyt` - EPANET Python wrapper
- `networkx` - Network graph manipulation
- `matplotlib` - Plotting and visualization
- `numpy` - Numerical computations
- `pandas` - Data manipulation
- `pillow` - Image processing

## 💻 Usage

### Running the GUIs

Each GUI can be run as a Python module:

```bash
# Tkinter GUI
python -m EpaNETTk

# Streamlit GUI
streamlit run EpaNETStreamlit/__main__.py
# or
python -m EpaNETStreamlit
```

### Using the Core Wrapper (`epanet_wrapper.py`)

The `EpanetWrapper` class provides a unified interface for EPANET operations:

```python
from pathlib import Path
from epanet_wrapper import EpanetWrapper
import matplotlib.pyplot as plt

# Initialize wrapper
epanet = EpanetWrapper()

# Load a network file
epanet.load_file(Path("samples/TESTING.inp"))

# Get network statistics
stats = epanet.get_statistics()
print(f"Nodes: {stats['node_count']}, Links: {stats['link_count']}")

# Run simulation
epanet.run_simulation()

# Plot network topology (NetworkX-based, default)
fig, ax = plt.subplots(figsize=(10, 8))
epanet.plot_network_topology(ax=ax, nodesID=True, linksID=True)
plt.show()

# Plot network with elevation
epanet.plot_network_attributes(ax=ax, attribute='elevation')
plt.show()

# Plot network with pressure (requires simulation)
epanet.plot_network_attributes(ax=ax, attribute='pressure', pressure_text=True)
plt.show()

# Plot time series for specific nodes
fig, ax = plt.subplots(figsize=(10, 6))
epanet.plot_time_series(
    ax=ax, 
    node_ids=['J1', 'J3', 'J5'],  # or node_indices=[1, 3, 5]
    plot_type='pressure', 
    time_unit='hours'
)
plt.show()

# Plot flow time series for links
epanet.plot_time_series(
    ax=ax,
    link_ids=['P1', 'P2'],  # or link_indices=[1, 2]
    plot_type='flow',
    time_unit='hours'
)
plt.show()

# Use EPyT native plotting
epanet.plot_network_topology(ax=ax, use_epyt_native=True, nodesID=True, linksID=True)
plt.show()

# Clean up
epanet.close()
```

### Key Methods

#### File Operations
- `load_file(file_path: Path)` - Load an EPANET `.inp` file
- `close()` - Close the network and free resources
- `is_loaded()` - Check if a file is currently loaded
- `get_file_name()` - Get the name of the loaded file
- `get_file_path()` - Get the path of the loaded file

#### Simulation
- `run_simulation()` - Run hydraulic and water quality simulation

#### Statistics
- `get_statistics()` - Get network metadata (node/link counts, names, elevations, coordinates)
- `get_node_attribute(node_id: str, attribute: str)` - Get specific node attribute

#### Visualization
- `plot_network_topology(ax, use_epyt_native=False, **kwargs)` - Plot network topology
- `plot_network_attributes(ax, attribute='elevation', use_epyt_native=False, **kwargs)` - Plot network with attribute coloring
  - `attribute`: 'elevation', 'pressure', 'flow', or 'quality'
- `plot_time_series(ax, node_ids=None, link_ids=None, node_indices=None, link_indices=None, plot_type='pressure', time_unit='hours')` - Plot time series data
  - `plot_type`: 'pressure', 'velocity', or 'flow'
  - Accepts both IDs (strings) and indices (integers)

## 🎨 GUI Features

### Tkinter GUI (`EpaNETTk`)

**Layout:**
- **Left Panel**: Compact control panel with toolbox, network stats, visualization options, and time series controls
- **Right Panel**: Interactive matplotlib canvas with click callouts

**Features:**
- File browser for loading `.inp` files
- Run simulation button
- Plot type selection (Topology, Elevation, Pressure, Flow, Quality)
- Show/hide labels toggle
- EPyT native plot toggle
- Interactive click callouts showing node/link information
- Click-to-populate time series input field
- Network information window with node/link IDs
- Real-time statistics display
- Time series plotting in separate window

**Interactive Features:**
- Click on nodes/links to see detailed information
- Callouts automatically populate time series input
- Click outside plot to clear callouts
- Smooth plot updates without canvas shrinking

### Streamlit GUI (`EpaNETStreamlit`)

**Layout:**
- **Sidebar**: Expandable sections for toolbox, network stats, visualization, and time series
- **Main Area**: Network plots and time series visualizations

**Features:**
- File uploader for `.inp` files
- Sample file quick-load buttons
- Run simulation button
- Plot type selection with radio buttons
- Show/hide labels toggle
- EPyT native plot toggle
- Network information expander with node/link browser
- Time series plotting with ID/index input
- Session state management for persistence

**Sidebar Sections:**
- **Toolbox** (expanded): File upload, simulation, options
- **Network Stats** (expanded): Node/link counts, simulation status
- **Visualization** (expanded): Plot type selection, update button
- **Time Series** (collapsed): Time series controls

## 🔧 Development

### Adding a New GUI

1. Create a new folder following the naming convention: `EpaNET[FrameworkName]`
2. Add `__init__.py` and `__main__.py` files
3. Create a requirements file in `requirements/[framework].in`
4. Import and use `EpanetWrapper` from `epanet_wrapper.py`
5. Implement the GUI-specific interface

Example structure:
```python
# EpaNETNewFramework/__main__.py
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_wrapper import EpanetWrapper

# Your GUI implementation here
```

### Requirements Management

Requirements are organized in the `requirements/` folder:
- `base.in` - Core dependencies (always included)
- `[gui].in` - GUI-specific dependencies (includes base)
- `dev.in` - Development tools

To compile requirements (if using pip-tools):
```bash
pip-compile requirements/base.in
pip-compile requirements/[gui].in
```

## 📝 Notes

- The core wrapper (`epanet_wrapper.py`) uses `Pathlib` for file operations (preferred over `os`)
- NetworkX is used for network graph construction and visualization (default)
- EPyT native plotting is available as an alternative visualization method
- Time series plotting supports both node/link IDs (strings) and indices (integers)
- All GUIs share the same core functionality through `EpanetWrapper`

## 🐛 Known Issues / Limitations

- EPyT native plotting has limited parameter support (some kwargs are filtered)
- Click callouts are currently only implemented in Tkinter GUI
- Some GUI implementations are placeholders and need full development

## 📄 License

See `LICENSE` file for details.

## 🙏 Acknowledgments

- **EPyT**: EPANET Python wrapper by KIOS Research
- **EPANET**: Water distribution system modeling software by US EPA
- GUI frameworks: Tkinter, Streamlit, PyQt, wxPython, Kivy, Flask, Flet, CustomTkinter

---

**Status**: Tkinter and Streamlit GUIs are functional. Other GUI implementations are placeholders ready for development.
