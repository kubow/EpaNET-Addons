"""Small reusable Tk widgets."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollFrame(ttk.Frame):
    """A vertically scrollable frame; put children in ``.body``."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, padding=(6, 4))
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.body.bind_all(seq, self._wheel, add="+")

    def _wheel(self, e):
        w = e.widget
        while w is not None:
            if w is self.body:
                break
            w = getattr(w, "master", None)
        else:
            return
        if isinstance(e.widget, (ttk.Combobox, tk.Listbox, ttk.Treeview)):
            return
        delta = -1 if (e.num == 4 or getattr(e, "delta", 0) > 0) else 1
        self.canvas.yview_scroll(delta, "units")


class Section(ttk.Frame):
    """A collapsible titled group."""

    def __init__(self, master, title: str, open_: bool = True):
        super().__init__(master)
        self._open = tk.BooleanVar(value=open_)
        self.header = ttk.Checkbutton(self, text=title, variable=self._open, style="Section.TCheckbutton",
                                      command=self._toggle)
        self.header.pack(fill="x", pady=(8, 2))
        self.body = ttk.Frame(self)
        if open_:
            self.body.pack(fill="x", padx=(4, 0))

    def _toggle(self):
        if self._open.get():
            self.body.pack(fill="x", padx=(4, 0))
        else:
            self.body.pack_forget()


class LabeledCombo(ttk.Frame):
    """Combobox that maps display labels to keys."""

    def __init__(self, master, label: str, command=None, width: int = 26):
        super().__init__(master)
        ttk.Label(self, text=label).pack(anchor="w")
        self.var = tk.StringVar()
        self.combo = ttk.Combobox(self, textvariable=self.var, state="readonly", width=width)
        self.combo.pack(fill="x")
        self._keys: list[str] = []
        self._labels: list[str] = []
        self.command = command
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.command and self.command(self.get()))

    def set_choices(self, pairs: list[tuple[str, str]], current: str | None = None):
        self._keys = [k for k, _ in pairs]
        self._labels = [lab for _, lab in pairs]
        self.combo["values"] = self._labels
        if current in self._keys:
            self.var.set(self._labels[self._keys.index(current)])
        elif self._labels:
            self.var.set(self._labels[0])

    def get(self) -> str:
        label = self.var.get()
        return self._keys[self._labels.index(label)] if label in self._labels else ""

    def set(self, key: str):
        if key in self._keys:
            self.var.set(self._labels[self._keys.index(key)])


def sortable_tree(tree: ttk.Treeview, numeric_cols: set[str] | None = None):
    """Make column headings sort the tree when clicked."""
    state = {"col": None, "rev": False}

    def sort(col):
        rev = state["rev"] if state["col"] != col else not state["rev"]
        state.update(col=col, rev=rev)
        items = [(tree.set(k, col), k) for k in tree.get_children("")]

        def key(item):
            v = item[0]
            try:
                return (0, float(v))
            except ValueError:
                return (1, v)
        items.sort(key=key, reverse=rev)
        for pos, (_, k) in enumerate(items):
            tree.move(k, "", pos)
    for col in tree["columns"]:
        tree.heading(col, command=lambda c=col: sort(c))
