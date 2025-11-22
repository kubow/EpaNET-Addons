# Requirements Structure

This folder contains organized requirements files for the EPANET GUI project.

## Base Requirements

- `base.in` - Core dependencies shared by all GUI implementations (epyt, networkx, matplotlib, numpy, pandas, pillow)

## GUI-Specific Requirements

### Desktop GUI Frameworks

- `tkinter.in` - Requirements for Tkinter GUI (includes base requirements + tk)
- `customtkinter.in` - Requirements for CustomTkinter GUI (includes base requirements + customtkinter) - Modern Tkinter with custom styling
- `pyqt.in` - Requirements for PyQt/PySide GUI (includes base requirements + PyQt6) - Qt-based cross-platform GUI
- `wxpython.in` - Requirements for wxPython GUI (includes base requirements + wxPython) - Native look and feel
- `kivy.in` - Requirements for Kivy GUI (includes base requirements + kivy) - Modern touch-friendly GUI

### Web-Based GUI Frameworks

- `streamlit.in` - Requirements for Streamlit GUI (includes base requirements + streamlit) - Simple web-based dashboard
- `flask.in` - Requirements for Flask web GUI (includes base requirements + Flask) - Full-featured web application
- `flet.in` - Requirements for Flet GUI (includes base requirements + flet) - Flutter-based cross-platform GUI

## Development Requirements

- `dev.in` - Development tools (includes base requirements + pip-tools)

## Usage

To install requirements for a specific GUI:

```bash
# Desktop GUIs
pip install -r requirements/tkinter.in
pip install -r requirements/customtkinter.in
pip install -r requirements/pyqt.in
pip install -r requirements/wxpython.in
pip install -r requirements/kivy.in

# Web-based GUIs
pip install -r requirements/streamlit.in
pip install -r requirements/flask.in
pip install -r requirements/flet.in

# Development tools
pip install -r requirements/dev.in
```

To compile requirements (if using pip-tools):

```bash
pip-compile requirements/base.in
pip-compile requirements/tkinter.in
pip-compile requirements/customtkinter.in
pip-compile requirements/pyqt.in
pip-compile requirements/wxpython.in
pip-compile requirements/kivy.in
pip-compile requirements/streamlit.in
pip-compile requirements/flask.in
pip-compile requirements/flet.in
```

## Running the GUIs

Each GUI can be run as a Python module:

```bash
# Desktop GUIs
python -m EpaNETTk
python -m EpaNETCustomTkinter
python -m EpaNETPyQt
python -m EpaNETwxPython
python -m EpaNETKivy

# Web-based GUIs
python -m EpaNETStreamlit
python -m EpaNETFlask
python -m EpaNETFlet
```

