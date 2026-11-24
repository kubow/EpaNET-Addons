"""ttk styling for a calm, readable engineering UI."""
from __future__ import annotations

import tkinter as tk
from tkinter import font, ttk

ACCENT = "#2563eb"
BG = "#f8fafc"
PANEL = "#ffffff"
MUTED = "#64748b"
TEXT = "#0f172a"


def apply(root: tk.Tk):
    s = ttk.Style(root)
    s.theme_use("clam")
    base = font.nametofont("TkDefaultFont")
    base.configure(size=10)
    root.configure(background=BG)
    s.configure(".", background=BG, foreground=TEXT, fieldbackground="white", bordercolor="#cbd5e1")
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background="white")
    s.configure("Card.TLabel", background="white")
    s.configure("Toolbar.TFrame", background="#e2e8f0")
    s.configure("Status.TFrame", background="#1e293b")
    s.configure("Status.TLabel", background="#1e293b", foreground="#e2e8f0", font=("TkDefaultFont", 9))
    s.configure("TLabel", background=BG)
    s.configure("Title.TLabel", font=("TkDefaultFont", 13, "bold"))
    s.configure("Section.TLabel", font=("TkDefaultFont", 10, "bold"), foreground="#1e3a8a")
    s.configure("Muted.TLabel", foreground=MUTED, font=("TkDefaultFont", 9))
    s.configure("Value.TLabel", font=("TkDefaultFont", 10, "bold"))
    s.configure("Section.TCheckbutton", font=("TkDefaultFont", 10, "bold"), foreground="#1e3a8a",
                indicatorsize=0, indicatormargin=0)
    s.configure("TButton", padding=(8, 3))
    s.configure("Tool.TButton", padding=(8, 3), background="#e2e8f0", bordercolor="#e2e8f0")
    s.map("Tool.TButton", background=[("active", "#cbd5e1")])
    s.configure("Chip.TButton", padding=(4, 0), font=("TkFixedFont", 9))
    s.configure("Crs.TButton", padding=(8, 3), font=("TkDefaultFont", 9, "bold"))
    s.configure("Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT, padding=(10, 3))
    s.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#93c5fd")])
    s.configure("Toolbutton", padding=(8, 3), background="#e2e8f0")
    s.map("Toolbutton", background=[("selected", "#bfdbfe"), ("active", "#cbd5e1")])
    s.configure("TNotebook", background=BG, borderwidth=0)
    s.configure("TNotebook.Tab", padding=(12, 5), font=("TkDefaultFont", 10))
    s.map("TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", ACCENT)])
    s.configure("Treeview", rowheight=22, font=("TkDefaultFont", 9))
    s.configure("Treeview.Heading", font=("TkDefaultFont", 9, "bold"))
