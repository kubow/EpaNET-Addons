.DEFAULT_GOAL := help

# Bootstrap a project environment; PYTHON can select an existing interpreter.
VENV ?= venv
BASE_PYTHON ?= python3
PYTHON ?= $(VENV)/bin/python
ARGS ?=

VARIANTS := tkinter customtkinter pyqt wxpython kivy streamlit flask flet
INSTALL_TARGETS := $(addprefix install-,$(VARIANTS))

.PHONY: help env $(VARIANTS) $(INSTALL_TARGETS)
.SECONDARY:

help:
	@printf '%s\n' \
	  'Run a GUI: make <variant>' \
	  'Variants: $(VARIANTS)' \
	  'First launch creates a virtual environment and installs dependencies.' \
	  '' \
	  'Create environment only: make env' \
	  'Install dependencies: make install-<variant>' \
	  'Python: $(PYTHON) (override with PYTHON=/path/to/python)' \
	  'Extra launch arguments: make <variant> ARGS="..."'

env: $(PYTHON)

$(PYTHON):
	"$(BASE_PYTHON)" -m venv "$(VENV)"

# Keep installation markers beside the selected interpreter, so environments
# cannot accidentally share dependency state. Reinstall when requirements change.
$(dir $(PYTHON)).epanet-%.installed: requirements/%.in requirements/base.in $(PYTHON)
	"$(PYTHON)" -m pip install -r requirements/$*.in
	@touch "$@"

$(VARIANTS): %: $(dir $(PYTHON)).epanet-%.installed

tkinter: MODULE = EpaNETTk
customtkinter: MODULE = EpaNETCustomTkinter
pyqt: MODULE = EpaNETPyQt
wxpython: MODULE = EpaNETwxPython
kivy: MODULE = EpaNETKivy
flask: MODULE = EpaNETFlask
flet: MODULE = EpaNETFlet

tkinter customtkinter pyqt wxpython kivy flask flet:
	"$(PYTHON)" -m $(MODULE) $(ARGS)

streamlit:
	"$(PYTHON)" -m streamlit run EpaNETStreamlit/__main__.py $(ARGS)

$(INSTALL_TARGETS): install-%: requirements/%.in requirements/base.in $(PYTHON)
	"$(PYTHON)" -m pip install -r requirements/$*.in
	@touch "$(dir $(PYTHON)).epanet-$*.installed"
