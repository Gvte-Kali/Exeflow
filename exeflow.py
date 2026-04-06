#!/usr/bin/env python3
"""
ExeFlow — Pentest Command Orchestrator
A variable-driven, shareable command sequencer built for Exegol and Linux pentesters.

Author  : Gvte-Kali
Repo    : https://github.com/Gvte-Kali/Exeflow
License : MIT
"""

import json
import os
import re
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

# ──────────────────────────────────────────────────────────────────────────────
#  ANSI COLOR PARSER
# ──────────────────────────────────────────────────────────────────────────────

ANSI_ESCAPE = re.compile(r"\x1b\[([0-9;]*)m")

ANSI_TAG_MAP = {
    "0":  "ansi_reset", "1":  "ansi_bold",
    "30": "ansi_black",          "31": "ansi_red",
    "32": "ansi_green",          "33": "ansi_yellow",
    "34": "ansi_blue",           "35": "ansi_magenta",
    "36": "ansi_cyan",           "37": "ansi_white",
    "90": "ansi_bright_black",   "91": "ansi_bright_red",
    "92": "ansi_bright_green",   "93": "ansi_bright_yellow",
    "94": "ansi_bright_blue",    "95": "ansi_bright_magenta",
    "96": "ansi_bright_cyan",    "97": "ansi_bright_white",
}


def parse_ansi(text: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    current_tag = ""
    last = 0
    for m in ANSI_ESCAPE.finditer(text):
        if m.start() > last:
            result.append((text[last:m.start()], current_tag))
        code = m.group(1)
        if code in ("", "0"):
            current_tag = ""
        else:
            for part in code.split(";"):
                if part in ANSI_TAG_MAP:
                    current_tag = ANSI_TAG_MAP[part]
        last = m.end()
    if last < len(text):
        result.append((text[last:], current_tag))
    return result or [(text, "")]


# ──────────────────────────────────────────────────────────────────────────────
#  EXEGOL ALIAS RESOLVER
# ──────────────────────────────────────────────────────────────────────────────

EXEGOL_ALIASES_PATH = "/opt/.exegol_aliases"


def _load_exegol_aliases(path: str = EXEGOL_ALIASES_PATH) -> dict[str, str]:
    aliases: dict[str, str] = {}
    if not os.path.exists(path):
        return aliases
    try:
        with open(path, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("function "):
                    continue
                m = re.match(r"""^alias\s+([A-Za-z0-9_.@-]+)=['"](.+)['"]$""", line)
                if m:
                    aliases[m.group(1)] = m.group(2)
    except Exception:
        pass
    return aliases


EXEGOL_ALIASES: dict[str, str] = _load_exegol_aliases()


def resolve_alias(cmd: str) -> str:
    if not EXEGOL_ALIASES:
        return cmd
    parts = cmd.strip().split(None, 1)
    if not parts:
        return cmd
    tool, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    if tool in EXEGOL_ALIASES:
        real = EXEGOL_ALIASES[tool]
        return f"{real} {rest}".strip() if rest else real
    return cmd


# ──────────────────────────────────────────────────────────────────────────────
#  THEME
# ──────────────────────────────────────────────────────────────────────────────

BG        = "#0d0f0e"
BG2       = "#131614"
BG3       = "#1a1d1b"
BG4       = "#222624"
BORDER    = "#2a2e2b"
GREEN     = "#39ff7e"
GREEN_DIM = "#1e7a42"
AMBER     = "#ffb347"
RED       = "#ff4f4f"
CYAN      = "#4fc3f7"
WHITE     = "#e8ede9"
GRAY      = "#6b7570"

FONT_MONO    = ("Monospace", 10)
FONT_MONO_SM = ("Monospace", 9)
FONT_TITLE   = ("Monospace", 14, "bold")

# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def resolve_command(template: str, variables: dict[str, str]) -> str:
    def replacer(m: re.Match) -> str:
        return variables.get(m.group(1).strip(), m.group(0))
    return re.sub(r"\{\{([^}]+)\}\}", replacer, template)


def get_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ──────────────────────────────────────────────────────────────────────────────
#  DATA MODELS
# ──────────────────────────────────────────────────────────────────────────────

class Variable:
    def __init__(self, name: str = "", value: str = "", description: str = ""):
        self.name        = name
        self.value       = value
        self.description = description

    def to_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "description": self.description}

    @staticmethod
    def from_dict(d: dict) -> "Variable":
        return Variable(d.get("name", ""), d.get("value", ""), d.get("description", ""))


class Command:
    def __init__(self, label: str = "", template: str = "",
                 description: str = "", enabled: bool = True):
        self.label       = label
        self.template    = template
        self.description = description
        self.enabled     = enabled

    def to_dict(self) -> dict:
        return {"label": self.label, "template": self.template,
                "description": self.description, "enabled": self.enabled}

    @staticmethod
    def from_dict(d: dict) -> "Command":
        return Command(d.get("label", ""), d.get("template", ""),
                       d.get("description", ""), d.get("enabled", True))


class Playbook:
    def __init__(self, name: str = "Unnamed Playbook", description: str = ""):
        self.name        = name
        self.description = description
        self.variables: list[Variable] = []
        self.commands:  list[Command]  = []

    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "variables": [v.to_dict() for v in self.variables],
            "commands":  [c.to_dict() for c in self.commands],
        }

    @staticmethod
    def from_dict(d: dict) -> "Playbook":
        pb = Playbook(d.get("name", "Unnamed"), d.get("description", ""))
        pb.variables = [Variable.from_dict(v) for v in d.get("variables", [])]
        pb.commands  = [Command.from_dict(c)  for c in d.get("commands",  [])]
        return pb

    def get_vars_dict(self) -> dict[str, str]:
        return {v.name: v.value for v in self.variables}


# ──────────────────────────────────────────────────────────────────────────────
#  SHARED STATE
# ──────────────────────────────────────────────────────────────────────────────

PLAYBOOKS_DIR: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
#  WIDGET HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def styled_btn(parent, text: str, command=None, color: str = GREEN,
               width: int | None = None, **kw) -> tk.Button:
    cfg = dict(text=text, command=command, bg=BG3, fg=color,
               activebackground=BG4, activeforeground=color,
               relief="flat", bd=0, font=FONT_MONO_SM,
               cursor="hand2", padx=8, pady=4)
    if width:
        cfg["width"] = width
    cfg.update(kw)
    btn = tk.Button(parent, **cfg)
    btn.bind("<Enter>", lambda e: btn.config(bg=BG4))
    btn.bind("<Leave>", lambda e: btn.config(bg=BG3))
    return btn


def separator(parent, color: str = BORDER, pady: int = 4) -> tk.Frame:
    f = tk.Frame(parent, bg=color, height=1)
    f.pack(fill="x", padx=8, pady=pady)
    return f


def section_label(parent, text: str, color: str = GREEN) -> tk.Frame:
    f = tk.Frame(parent, bg=BG)
    f.pack(fill="x", padx=8, pady=(8, 2))
    tk.Label(f, text=text, bg=BG, fg=color, font=FONT_MONO_SM).pack(side="left")
    tk.Frame(f, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(6, 0))
    return f


def make_text_widget(parent) -> tk.Text:
    """Create a styled, scrollable read-only terminal Text widget."""
    frame = tk.Frame(parent, bg=BG2, highlightthickness=1, highlightbackground=BORDER)
    frame.pack(fill="both", expand=True)

    txt = tk.Text(frame, bg=BG2, fg=GREEN, font=FONT_MONO_SM,
                  insertbackground=GREEN, relief="flat", bd=6,
                  state="disabled", wrap="none")
    ysb = ttk.Scrollbar(frame, orient="vertical",   command=txt.yview)
    xsb = ttk.Scrollbar(frame, orient="horizontal", command=txt.xview)
    txt.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
    xsb.pack(side="bottom", fill="x")
    ysb.pack(side="right",  fill="y")
    txt.pack(fill="both", expand=True)

    # Standard tags
    txt.tag_configure("header",  foreground=CYAN, font=("Monospace", 10, "bold"))
    txt.tag_configure("success", foreground=GREEN)
    txt.tag_configure("error",   foreground=RED)
    txt.tag_configure("warn",    foreground=AMBER)
    txt.tag_configure("dim",     foreground=GRAY)
    txt.tag_configure("stdout",  foreground=WHITE)

    # ANSI tags
    ansi_colors = {
        "ansi_reset": WHITE, "ansi_bold": WHITE,
        "ansi_black": "#555555", "ansi_red": "#ff5555",
        "ansi_green": "#50fa7b", "ansi_yellow": "#f1fa8c",
        "ansi_blue": "#6272a4", "ansi_magenta": "#ff79c6",
        "ansi_cyan": "#8be9fd", "ansi_white": "#f8f8f2",
        "ansi_bright_black": "#6272a4", "ansi_bright_red": "#ff6e6e",
        "ansi_bright_green": "#69ff94", "ansi_bright_yellow": "#ffffa5",
        "ansi_bright_blue": "#d6acff", "ansi_bright_magenta": "#ff92df",
        "ansi_bright_cyan": "#a4ffff", "ansi_bright_white": "#ffffff",
    }
    for tag, color in ansi_colors.items():
        kw: dict = {"foreground": color}
        if tag == "ansi_bold":
            kw["font"] = ("Monospace", 9, "bold")
        txt.tag_configure(tag, **kw)

    return txt


# ──────────────────────────────────────────────────────────────────────────────
#  VARIABLE EDITOR DIALOG
# ──────────────────────────────────────────────────────────────────────────────

class VarDialog(tk.Toplevel):
    def __init__(self, parent, variable: Variable | None = None):
        super().__init__(parent)
        self.result: Variable | None = None
        self.title("Variable Editor")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        var = variable or Variable()

        tk.Label(self, text="┌─ VARIABLE ─────────────────────",
                 bg=BG, fg=GREEN, font=FONT_MONO_SM).pack(anchor="w", padx=12, pady=(12, 4))

        for label, attr in [("Name", "name"), ("Value", "value"), ("Description", "description")]:
            tk.Label(self, text=f"  {label}:", bg=BG, fg=GRAY,
                     font=FONT_MONO_SM).pack(anchor="w", padx=12)
            entry = tk.Entry(self, bg=BG3, fg=WHITE, insertbackground=GREEN, font=FONT_MONO,
                             relief="flat", bd=0, highlightthickness=1,
                             highlightbackground=BORDER, highlightcolor=GREEN)
            entry.insert(0, getattr(var, attr))
            entry.pack(fill="x", padx=12, pady=(0, 6))
            setattr(self, f"e_{attr}", entry)

        tk.Label(self, text="  Syntax: {{NAME}} in commands",
                 bg=BG, fg=GREEN_DIM, font=FONT_MONO_SM).pack(anchor="w", padx=12, pady=(0, 8))

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12, pady=(0, 12))
        styled_btn(row, "✓ Save",   self._save,   color=GREEN).pack(side="right", padx=4)
        styled_btn(row, "✗ Cancel", self.destroy, color=GRAY).pack(side="right")
        self.e_name.focus_set()

    def _save(self):
        name = self.e_name.get().strip()
        if not name:
            messagebox.showerror("Error", "Variable name required.", parent=self); return
        if not re.match(r"^[A-Za-z0-9_]+$", name):
            messagebox.showerror("Error", "Name: alphanumeric + underscore only.", parent=self); return
        self.result = Variable(name, self.e_value.get(), self.e_description.get())
        self.destroy()


# ──────────────────────────────────────────────────────────────────────────────
#  COMMAND EDITOR DIALOG
# ──────────────────────────────────────────────────────────────────────────────

class CmdDialog(tk.Toplevel):
    def __init__(self, parent, command: Command | None = None,
                 variables: list[Variable] | None = None):
        super().__init__(parent)
        self.result: Command | None = None
        self.title("Command Editor")
        self.configure(bg=BG)
        self.resizable(True, False)
        self.minsize(560, 0)
        self.grab_set()
        cmd   = command or Command()
        vars_ = variables or []

        tk.Label(self, text="┌─ COMMAND ──────────────────────",
                 bg=BG, fg=CYAN, font=FONT_MONO_SM).pack(anchor="w", padx=12, pady=(12, 4))

        for label, attr in [("Label", "label"), ("Description", "description")]:
            tk.Label(self, text=f"  {label}:", bg=BG, fg=GRAY,
                     font=FONT_MONO_SM).pack(anchor="w", padx=12)
            entry = tk.Entry(self, bg=BG3, fg=WHITE, insertbackground=GREEN, font=FONT_MONO,
                             relief="flat", bd=0, highlightthickness=1,
                             highlightbackground=BORDER, highlightcolor=CYAN)
            entry.insert(0, getattr(cmd, attr))
            entry.pack(fill="x", padx=12, pady=(0, 6))
            setattr(self, f"e_{attr}", entry)

        tk.Label(self, text="  Command template:", bg=BG, fg=GRAY,
                 font=FONT_MONO_SM).pack(anchor="w", padx=12)
        self.e_template = tk.Text(self, bg=BG3, fg=WHITE, insertbackground=GREEN, font=FONT_MONO,
                                  relief="flat", bd=0, highlightthickness=1,
                                  highlightbackground=BORDER, highlightcolor=CYAN,
                                  height=4, wrap="none")
        self.e_template.insert("1.0", cmd.template)
        self.e_template.pack(fill="x", padx=12, pady=(0, 8))

        if vars_:
            tk.Label(self, text="  Insert variable:", bg=BG, fg=GRAY,
                     font=FONT_MONO_SM).pack(anchor="w", padx=12)
            vf = tk.Frame(self, bg=BG)
            vf.pack(fill="x", padx=12, pady=(0, 8))
            for v in vars_:
                tag = "{{" + v.name + "}}"
                def _insert(t=tag):
                    self.e_template.insert("insert", t)
                    self.e_template.focus_set()
                styled_btn(vf, v.name, _insert, color=AMBER, pady=2).pack(side="left", padx=(0, 4))

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12, pady=(0, 12))
        styled_btn(row, "✓ Save",   self._save,   color=CYAN).pack(side="right", padx=4)
        styled_btn(row, "✗ Cancel", self.destroy, color=GRAY).pack(side="right")
        self.e_label.focus_set()

    def _save(self):
        label    = self.e_label.get().strip()
        template = self.e_template.get("1.0", "end-1c").strip()
        if not label:
            messagebox.showerror("Error", "Label required.", parent=self); return
        if not template:
            messagebox.showerror("Error", "Command template required.", parent=self); return
        self.result = Command(label, template, self.e_description.get().strip())
        self.destroy()


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN APPLICATION
# ──────────────────────────────────────────────────────────────────────────────

class ExeFlow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ExeFlow — Pentest Command Orchestrator")
        self.configure(bg=BG)
        self.geometry("1280x820")
        self.minsize(900, 600)

        self.playbook        = Playbook("New Playbook")
        self._running        = False
        self._stop_requested = False
        self._checked:       dict[int, bool] = {}
        self._select_all_var = tk.BooleanVar(value=False)

        # Per-command output buffers  {label: [(text, tag), ...]}
        self._cmd_buffers:      dict[str, list] = {}
        self._cmd_order:        list[str]       = []   # ordered list of labels
        self._active_tab:       str | None      = None
        self._tab_btns:         dict[str, tk.Label] = {}

        self._build_ui()
        self._apply_ttk_style()
        self._refresh_all()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_topbar()
        self._build_statusbar()
        self._build_panes()

    def _build_topbar(self):
        bar = tk.Frame(self, bg=BG2, height=44)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="⬡ EXEFLOW", bg=BG2, fg=GREEN,
                 font=FONT_TITLE, padx=16).pack(side="left", pady=6)
        tk.Label(bar, text="command orchestrator", bg=BG2, fg=GREEN_DIM,
                 font=FONT_MONO_SM).pack(side="left")
        tk.Label(bar, text="│", bg=BG2, fg=BORDER,
                 font=("Monospace", 14, "bold")).pack(side="left", padx=8)

        self.pb_name_var = tk.StringVar(value=self.playbook.name)
        name_entry = tk.Entry(bar, textvariable=self.pb_name_var, bg=BG2, fg=AMBER,
                              insertbackground=AMBER, font=("Monospace", 11, "bold"),
                              relief="flat", bd=0, width=28)
        name_entry.pack(side="left")
        name_entry.bind("<FocusOut>",
                        lambda e: setattr(self.playbook, "name", self.pb_name_var.get()))

        for text, cmd, color in [
            ("⬇ Export",           self._export,                WHITE),
            ("⬆ Import",           self._import,                WHITE),
            ("📁 Playbooks Folder", self._pick_playbooks_folder, WHITE),
        ]:
            styled_btn(bar, text, cmd, color=color).pack(side="right", padx=3, pady=6)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=BG2, height=24)
        bar.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="ready")
        tk.Label(bar, textvariable=self.status_var,
                 bg=BG2, fg=GREEN_DIM, font=FONT_MONO_SM, padx=8).pack(side="left")
        self.progress_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.progress_var,
                 bg=BG2, fg=AMBER, font=FONT_MONO_SM, padx=8).pack(side="right")

    def _build_panes(self):
        self._paned = tk.PanedWindow(self, orient="horizontal", bg=BORDER,
                                     sashwidth=5, relief="flat", bd=0)
        self._paned.pack(fill="both", expand=True)

        left  = tk.Frame(self._paned, bg=BG)
        right = tk.Frame(self._paned, bg=BG)
        self._paned.add(left,  minsize=300)
        self._paned.add(right, minsize=400)

        self._build_left(left)
        self._build_right(right)
        self.after(100, self._set_sash_center)

    def _set_sash_center(self):
        w = self._paned.winfo_width()
        if w > 10:
            self._paned.sash_place(0, w // 2, 0)
        else:
            self.after(100, self._set_sash_center)

    # ── LEFT PANEL ────────────────────────────────────────────────────────────

    def _build_left(self, parent):
        section_label(parent, "[ VARIABLES ]", GREEN)

        tb = tk.Frame(parent, bg=BG)
        tb.pack(fill="x", padx=8, pady=(0, 4))
        styled_btn(tb, "+ Add",  self._add_variable,  color=GREEN, pady=2).pack(side="left")
        styled_btn(tb, "✎ Edit", self._edit_variable, color=WHITE, pady=2).pack(side="left", padx=4)
        styled_btn(tb, "✗ Del",  self._del_variable,  color=RED,   pady=2).pack(side="left")

        vf = tk.Frame(parent, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        vf.pack(fill="x", padx=8, pady=(0, 4))

        self.var_tree = ttk.Treeview(vf, columns=("Name", "Value", "Desc"),
                                     show="headings", height=7, selectmode="browse")
        self.var_tree.heading("Name",  text="NAME")
        self.var_tree.heading("Value", text="VALUE")
        self.var_tree.heading("Desc",  text="DESCRIPTION")
        self.var_tree.column("Name",  width=90,  stretch=False)
        self.var_tree.column("Value", width=100, stretch=False)
        self.var_tree.column("Desc",  width=120)
        self.var_tree.pack(fill="both", expand=True)
        self.var_tree.bind("<Double-1>", lambda e: self._edit_variable())
        self._style_tree(self.var_tree)

        separator(parent, pady=4)
        section_label(parent, "[ COMMANDS ]", CYAN)

        tb2 = tk.Frame(parent, bg=BG)
        tb2.pack(fill="x", padx=8, pady=(0, 2))
        styled_btn(tb2, "+ Add",  self._add_command,  color=CYAN,  pady=2).pack(side="left")
        styled_btn(tb2, "✎ Edit", self._edit_command, color=WHITE, pady=2).pack(side="left", padx=4)
        styled_btn(tb2, "✗ Del",  self._del_command,  color=RED,   pady=2).pack(side="left")
        styled_btn(tb2, "↑", self._cmd_up,   color=WHITE, pady=2, width=2).pack(side="left", padx=(8, 2))
        styled_btn(tb2, "↓", self._cmd_down, color=WHITE, pady=2, width=2).pack(side="left")

        # Select-all row
        sel_row = tk.Frame(parent, bg=BG)
        sel_row.pack(fill="x", padx=8, pady=(2, 2))
        self._sel_all_cb = tk.Checkbutton(
            sel_row, text="Select / Deselect All",
            variable=self._select_all_var,
            command=self._toggle_select_all,
            bg=BG, fg=WHITE, selectcolor=BG3,
            activebackground=BG, font=FONT_MONO_SM,
        )
        self._sel_all_cb.pack(side="left")

        # Scrollable command rows
        cf_outer = tk.Frame(parent, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        cf_outer.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self._cmd_canvas = tk.Canvas(cf_outer, bg=BG3, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(cf_outer, orient="vertical", command=self._cmd_canvas.yview)
        self._cmd_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._cmd_canvas.pack(side="left", fill="both", expand=True)

        self._cmd_rows_frame = tk.Frame(self._cmd_canvas, bg=BG3)
        self._cmd_canvas_win = self._cmd_canvas.create_window(
            (0, 0), window=self._cmd_rows_frame, anchor="nw")

        self._cmd_rows_frame.bind("<Configure>", lambda e: self._cmd_canvas.configure(
            scrollregion=self._cmd_canvas.bbox("all")))
        self._cmd_canvas.bind("<Configure>", lambda e: self._cmd_canvas.itemconfig(
            self._cmd_canvas_win, width=e.width))

        def _fwd_scroll(e):
            if e.num == 4:   self._cmd_canvas.yview_scroll(-1, "units")
            elif e.num == 5: self._cmd_canvas.yview_scroll(1,  "units")
            else:            self._cmd_canvas.yview_scroll(int(-e.delta / 120), "units")
        self._cmd_canvas.bind("<Button-4>",   _fwd_scroll)
        self._cmd_canvas.bind("<Button-5>",   _fwd_scroll)
        self._cmd_canvas.bind("<MouseWheel>", _fwd_scroll)
        self._scroll_fwd = _fwd_scroll

    # ── RIGHT PANEL ───────────────────────────────────────────────────────────

    def _build_right(self, parent):
        # ── Toolbar row 1: Run / Stop controls
        run_bar = tk.Frame(parent, bg=BG2)
        run_bar.pack(fill="x", padx=0, pady=(0, 0))

        tk.Label(run_bar, text=" RUN", bg=BG2, fg=GREEN_DIM,
                 font=FONT_MONO_SM).pack(side="left", padx=(8, 4), pady=4)
        styled_btn(run_bar, "▶ Run Checked",  self._run_checked,  color=GREEN, pady=3).pack(side="left", padx=2, pady=4)
        styled_btn(run_bar, "▶▶ Run All",      self._run_all,      color=GREEN, pady=3).pack(side="left", padx=2, pady=4)
        styled_btn(run_bar, "⟳ Run Parallel",  self._run_parallel, color=AMBER, pady=3).pack(side="left", padx=2, pady=4)
        styled_btn(run_bar, "■ Stop",           self._stop,         color=RED,   pady=3).pack(side="left", padx=2, pady=4)

        # ── Toolbar row 2: Output controls
        out_bar = tk.Frame(parent, bg=BG3)
        out_bar.pack(fill="x", padx=0, pady=(0, 0))

        tk.Label(out_bar, text=" OUTPUT", bg=BG3, fg=GREEN_DIM,
                 font=FONT_MONO_SM).pack(side="left", padx=(8, 4), pady=4)
        styled_btn(out_bar, "💾 Save Tab",  self._save_tab,   color=CYAN,  pady=3).pack(side="left", padx=2, pady=4)
        styled_btn(out_bar, "💾 Save All",  self._save_all,   color=CYAN,  pady=3).pack(side="left", padx=2, pady=4)
        styled_btn(out_bar, "⌫ Clear Tab",  self._clear_tab,  color=WHITE, pady=3).pack(side="left", padx=2, pady=4)
        styled_btn(out_bar, "⌫ Clear All",  self._clear_all,  color=WHITE, pady=3).pack(side="left", padx=2, pady=4)

        self.autoscroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(out_bar, text="Auto-scroll", variable=self.autoscroll_var,
                       bg=BG3, fg=WHITE, selectcolor=BG4,
                       activebackground=BG3, font=FONT_MONO_SM).pack(side="left", padx=(8, 2), pady=4)

        self.timestamp_var = tk.BooleanVar(value=True)
        tk.Checkbutton(out_bar, text="Timestamps", variable=self.timestamp_var,
                       bg=BG3, fg=WHITE, selectcolor=BG4,
                       activebackground=BG3, font=FONT_MONO_SM).pack(side="left", padx=2, pady=4)

        # ── Main content: tabs sidebar + output terminal
        content = tk.Frame(parent, bg=BG)
        content.pack(fill="both", expand=True, padx=0, pady=0)

        # Tabs sidebar (left side of output area)
        self._tabs_sidebar = tk.Frame(content, bg=BG2, width=160)
        self._tabs_sidebar.pack(side="left", fill="y")
        self._tabs_sidebar.pack_propagate(False)

        tk.Label(self._tabs_sidebar, text="[ TABS ]", bg=BG2, fg=CYAN,
                 font=FONT_MONO_SM).pack(fill="x", padx=6, pady=(6, 2))
        tk.Frame(self._tabs_sidebar, bg=BORDER, height=1).pack(fill="x", padx=4)

        tab_scroll_frame = tk.Frame(self._tabs_sidebar, bg=BG2)
        tab_scroll_frame.pack(fill="both", expand=True)

        self._tab_canvas = tk.Canvas(tab_scroll_frame, bg=BG2, highlightthickness=0, bd=0)
        tab_vsb = ttk.Scrollbar(tab_scroll_frame, orient="vertical", command=self._tab_canvas.yview)
        self._tab_canvas.configure(yscrollcommand=tab_vsb.set)
        tab_vsb.pack(side="right", fill="y")
        self._tab_canvas.pack(side="left", fill="both", expand=True)

        self._tab_list_frame = tk.Frame(self._tab_canvas, bg=BG2)
        self._tab_canvas_win = self._tab_canvas.create_window(
            (0, 0), window=self._tab_list_frame, anchor="nw")
        self._tab_list_frame.bind("<Configure>", lambda e: self._tab_canvas.configure(
            scrollregion=self._tab_canvas.bbox("all")))
        self._tab_canvas.bind("<Configure>", lambda e: self._tab_canvas.itemconfig(
            self._tab_canvas_win, width=e.width))

        # Vertical separator
        tk.Frame(content, bg=BORDER, width=1).pack(side="left", fill="y")

        # Output terminal
        term_container = tk.Frame(content, bg=BG)
        term_container.pack(side="left", fill="both", expand=True)

        self.output = make_text_widget(term_container)

    def _apply_ttk_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview",
                    background=BG3, foreground=WHITE, fieldbackground=BG3,
                    borderwidth=0, rowheight=22, font=FONT_MONO_SM)
        s.configure("Treeview.Heading",
                    background=BG4, foreground=GRAY, borderwidth=0, font=FONT_MONO_SM)
        s.map("Treeview",
              background=[("selected", BG4)],
              foreground=[("selected", WHITE)])
        s.configure("Vertical.TScrollbar",
                    background=BG3, troughcolor=BG2, borderwidth=0, arrowsize=12)
        s.configure("Horizontal.TScrollbar",
                    background=BG3, troughcolor=BG2, borderwidth=0, arrowsize=12)

    def _style_tree(self, tree: ttk.Treeview):
        tree.tag_configure("disabled", foreground=GRAY)
        tree.tag_configure("enabled",  foreground=WHITE)

    # ── REFRESH ───────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._refresh_vars()
        self._refresh_cmds()

    def _refresh_vars(self):
        self.var_tree.delete(*self.var_tree.get_children())
        for v in self.playbook.variables:
            self.var_tree.insert("", "end", values=(v.name, v.value, v.description))

    def _refresh_cmds(self):
        # Preserve checked state by label
        old_checked: dict[str, bool] = {
            self.playbook.commands[i].label: self._checked.get(i, False)
            for i in range(len(self.playbook.commands))
        }

        for w in self._cmd_rows_frame.winfo_children():
            w.destroy()
        self._checked.clear()

        vd = self.playbook.get_vars_dict()
        for i, cmd in enumerate(self.playbook.commands):
            checked = old_checked.get(cmd.label, False)
            self._checked[i] = checked
            self._build_cmd_row(i, cmd, checked, vd)

        # Sync select-all checkbox state
        if self.playbook.commands:
            all_checked = all(self._checked.get(i, False)
                              for i in range(len(self.playbook.commands)))
            self._select_all_var.set(all_checked)

        self._cmd_canvas.update_idletasks()
        self._cmd_canvas.configure(scrollregion=self._cmd_canvas.bbox("all"))

    def _build_cmd_row(self, idx: int, cmd: Command, checked: bool, vd: dict):
        row = tk.Frame(self._cmd_rows_frame, bg=BG3,
                       highlightthickness=1,
                       highlightbackground=CYAN if checked else BORDER)
        row.pack(fill="x", pady=2, padx=2)

        # Large checkbox
        chk_lbl = tk.Label(row, text="☑" if checked else "☐",
                           bg=BG3, fg=GREEN if checked else GRAY,
                           font=("Monospace", 15), cursor="hand2",
                           width=2, anchor="center")
        chk_lbl.pack(side="left", padx=(6, 2), pady=6)

        # Text content
        txt_frame = tk.Frame(row, bg=BG3)
        txt_frame.pack(side="left", fill="both", expand=True, pady=6, padx=(0, 8))

        label_color = CYAN if checked else (GRAY if not cmd.enabled else WHITE)
        lbl = tk.Label(txt_frame, text=cmd.label, bg=BG3, fg=label_color,
                       font=("Monospace", 9, "bold"), anchor="w")
        lbl.pack(fill="x")

        preview = resolve_command(cmd.template, vd)
        cmd_lbl = tk.Label(txt_frame, text=preview, bg=BG3, fg=GRAY,
                           font=("Monospace", 8), anchor="w", justify="left",
                           wraplength=1)
        cmd_lbl.pack(fill="x")

        def toggle(event=None, _idx=idx):
            self._checked[_idx] = not self._checked.get(_idx, False)
            self._refresh_cmds()

        def dbl(event=None, _idx=idx):
            self._edit_command_by_idx(_idx)

        for w in (row, chk_lbl, txt_frame, lbl, cmd_lbl):
            w.bind("<Button-1>",       toggle)
            w.bind("<Double-Button-1>", dbl)
            w.bind("<Button-4>",        self._scroll_fwd)
            w.bind("<Button-5>",        self._scroll_fwd)
            w.bind("<MouseWheel>",      self._scroll_fwd)

        def _wrap(event, lbl=cmd_lbl):
            w = event.width - 16
            if w > 20:
                lbl.config(wraplength=w)
        txt_frame.bind("<Configure>", _wrap)

    # ── SELECT ALL ────────────────────────────────────────────────────────────

    def _toggle_select_all(self):
        val = self._select_all_var.get()
        for idx in range(len(self.playbook.commands)):
            self._checked[idx] = val
        self._refresh_cmds()
        # Re-set the var since _refresh_cmds recalculates it
        self._select_all_var.set(val)

    def _get_checked_indices(self) -> list[int]:
        return [i for i, v in self._checked.items() if v]

    # ── TABS ──────────────────────────────────────────────────────────────────

    def _init_run_buffers(self, labels: list[str]):
        """Set up per-command output buffers and tab buttons for a new run."""
        self._cmd_buffers = {label: [] for label in labels}
        self._cmd_order   = labels
        self._tab_btns    = {}

        # Clear old tab buttons
        for w in self._tab_list_frame.winfo_children():
            w.destroy()

        for label in labels:
            btn = tk.Label(self._tab_list_frame, text=label,
                           bg=BG3, fg=WHITE, font=FONT_MONO_SM,
                           anchor="w", cursor="hand2",
                           padx=8, pady=6, wraplength=140, justify="left")
            btn.pack(fill="x", pady=1, padx=2)
            self._tab_btns[label] = btn

            def _click(e, l=label):
                self._switch_tab(l)
            btn.bind("<Button-1>", _click)

        # Activate first tab
        if labels:
            self._switch_tab(labels[0])

    def _switch_tab(self, label: str):
        self._active_tab = label
        for lbl, btn in self._tab_btns.items():
            if lbl == label:
                btn.config(bg=BG4, fg=AMBER,
                           highlightthickness=1, highlightbackground=AMBER)
            else:
                btn.config(bg=BG3, fg=WHITE, highlightthickness=0)
        self._redraw_active_tab()

    def _redraw_active_tab(self):
        label = self._active_tab
        if label is None:
            return
        buf = self._cmd_buffers.get(label, [])
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        for text, tag in buf:
            self._insert_line(text, tag)
        self.output.config(state="disabled")
        if self.autoscroll_var.get():
            self.output.see("end")

    def _tab_log(self, label: str, text: str, tag: str = "stdout"):
        """Append a line to a command's buffer and refresh if it's the active tab."""
        self._cmd_buffers[label].append((text, tag))
        if self._active_tab == label:
            self.after(0, lambda t=text, tg=tag: self._append_line(t, tg))

    # ── OUTPUT ────────────────────────────────────────────────────────────────

    def _insert_line(self, text: str, tag: str):
        """Insert one line into the output widget (must be called with state=normal)."""
        if self.timestamp_var.get() and tag in ("header", "warn", "error"):
            self.output.insert("end", f"[{get_timestamp()}] ", "dim")
        if tag == "stdout" and ANSI_ESCAPE.search(text):
            chunks = parse_ansi(text)
            for i, (chunk, ansi_tag) in enumerate(chunks):
                t = ansi_tag or "stdout"
                self.output.insert("end", chunk + ("\n" if i == len(chunks) - 1 else ""), t)
        else:
            self.output.insert("end", text + "\n", tag)

    def _append_line(self, text: str, tag: str):
        """Append one line to the live output widget."""
        self.output.config(state="normal")
        self._insert_line(text, tag)
        self.output.config(state="disabled")
        if self.autoscroll_var.get():
            self.output.see("end")

    def _clear_tab(self):
        if self._active_tab and self._active_tab in self._cmd_buffers:
            self._cmd_buffers[self._active_tab].clear()
            self.output.config(state="normal")
            self.output.delete("1.0", "end")
            self.output.config(state="disabled")

    def _clear_all(self):
        for label in self._cmd_buffers:
            self._cmd_buffers[label].clear()
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.config(state="disabled")

    def _save_tab(self):
        label = self._active_tab
        if not label or label not in self._cmd_buffers:
            messagebox.showinfo("Save Tab", "No active tab to save.")
            return
        self._save_buffer(self._cmd_buffers[label],
                          f"exeflow_{label.replace(' ', '_')}")

    def _save_all(self):
        if not self._cmd_buffers:
            messagebox.showinfo("Save All", "No output to save.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("Log file", "*.log"), ("All", "*.*")],
            initialdir=PLAYBOOKS_DIR or os.path.expanduser("~"),
            initialfile=f"exeflow_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                for label in self._cmd_order:
                    f.write(f"{'='*60}\n# {label}\n{'='*60}\n")
                    for text, _ in self._cmd_buffers.get(label, []):
                        f.write(ANSI_ESCAPE.sub("", text) + "\n")
                    f.write("\n")
            self._tab_log(self._active_tab or "", f"All output saved → {path}", "success")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _save_buffer(self, buf: list, default_name: str):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("Log file", "*.log"), ("All", "*.*")],
            initialdir=PLAYBOOKS_DIR or os.path.expanduser("~"),
            initialfile=f"{default_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                for text, _ in buf:
                    f.write(ANSI_ESCAPE.sub("", text) + "\n")
            self._append_line(f"Output saved → {path}", "success")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    # ── VARIABLE ACTIONS ──────────────────────────────────────────────────────

    def _add_variable(self):
        dlg = VarDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            if dlg.result.name in {v.name for v in self.playbook.variables}:
                messagebox.showerror("Error", f"Variable '{dlg.result.name}' already exists.")
                return
            self.playbook.variables.append(dlg.result)
            self._refresh_vars()
            self._refresh_cmds()

    def _edit_variable(self):
        idx = self._get_selected_var_idx()
        if idx is None:
            return
        dlg = VarDialog(self, self.playbook.variables[idx])
        self.wait_window(dlg)
        if dlg.result:
            self.playbook.variables[idx] = dlg.result
            self._refresh_vars()
            self._refresh_cmds()

    def _del_variable(self):
        idx = self._get_selected_var_idx()
        if idx is None:
            return
        name = self.playbook.variables[idx].name
        if messagebox.askyesno("Delete Variable", f"Delete variable '{name}'?"):
            del self.playbook.variables[idx]
            self._refresh_vars()
            self._refresh_cmds()

    def _get_selected_var_idx(self) -> int | None:
        sel = self.var_tree.selection()
        if not sel:
            return None
        return list(self.var_tree.get_children()).index(sel[0])

    # ── COMMAND ACTIONS ───────────────────────────────────────────────────────

    def _add_command(self):
        dlg = CmdDialog(self, variables=self.playbook.variables)
        self.wait_window(dlg)
        if dlg.result:
            self.playbook.commands.append(dlg.result)
            self._refresh_cmds()

    def _edit_command(self):
        checked = self._get_checked_indices()
        if checked:
            self._edit_command_by_idx(checked[0])
        else:
            messagebox.showinfo("Edit Command",
                                "Check a command first, or double-click its row.")

    def _edit_command_by_idx(self, idx: int):
        dlg = CmdDialog(self, self.playbook.commands[idx], self.playbook.variables)
        self.wait_window(dlg)
        if dlg.result:
            dlg.result.enabled = self.playbook.commands[idx].enabled
            self.playbook.commands[idx] = dlg.result
            self._refresh_cmds()

    def _del_command(self):
        checked = self._get_checked_indices()
        if not checked:
            messagebox.showinfo("Delete Command", "Check at least one command to delete.")
            return
        labels = [self.playbook.commands[i].label for i in checked]
        msg = f"Delete {len(checked)} command(s)?\n" + "\n".join(f"  • {l}" for l in labels)
        if messagebox.askyesno("Delete Commands", msg):
            for i in sorted(checked, reverse=True):
                del self.playbook.commands[i]
            self._checked.clear()
            self._refresh_cmds()

    def _cmd_up(self):
        checked = self._get_checked_indices()
        if not checked or checked[0] == 0:
            return
        idx = checked[0]
        c = self.playbook.commands
        c[idx - 1], c[idx] = c[idx], c[idx - 1]
        self._checked[idx - 1], self._checked[idx] = (
            self._checked.get(idx, False), self._checked.get(idx - 1, False))
        self._refresh_cmds()

    def _cmd_down(self):
        checked = self._get_checked_indices()
        if not checked or checked[-1] >= len(self.playbook.commands) - 1:
            return
        idx = checked[-1]
        c = self.playbook.commands
        c[idx + 1], c[idx] = c[idx], c[idx + 1]
        self._checked[idx + 1], self._checked[idx] = (
            self._checked.get(idx, False), self._checked.get(idx + 1, False))
        self._refresh_cmds()

    # ── EXECUTION ─────────────────────────────────────────────────────────────

    def _build_cmd_list(self, indices) -> list[tuple[str, str]]:
        vd = self.playbook.get_vars_dict()
        return [(self.playbook.commands[i].label,
                 resolve_command(self.playbook.commands[i].template, vd))
                for i in indices]

    def _run_checked(self):
        checked = self._get_checked_indices()
        if not checked:
            self._append_line("No commands checked. Check at least one.", "warn")
            return
        self._execute_sequential(self._build_cmd_list(checked))

    def _run_all(self):
        if not self.playbook.commands:
            self._append_line("No commands in playbook.", "warn")
            return
        self._execute_sequential(self._build_cmd_list(range(len(self.playbook.commands))))

    def _run_parallel(self):
        checked = self._get_checked_indices()
        if not checked:
            self._append_line("No commands checked for parallel run.", "warn")
            return
        self._execute_parallel(self._build_cmd_list(checked))

    def _stop(self):
        self._stop_requested = True
        if self._active_tab:
            self._tab_log(self._active_tab, "── Stop requested ──", "warn")

    def _execute_sequential(self, commands: list[tuple[str, str]]):
        if self._running:
            self._append_line("Already running. Stop first.", "warn")
            return
        self._running        = True
        self._stop_requested = False

        labels = [label for label, _ in commands]
        self.after(0, lambda: self._init_run_buffers(labels))

        def run():
            total = len(commands)
            for i, (label, cmd) in enumerate(commands):
                if self._stop_requested:
                    self.after(0, lambda l=label: self._tab_log(l, "── Stopped by user ──", "warn"))
                    break
                self.after(0, lambda l=label, n=i + 1, t=total: (
                    self.status_var.set(f"running: {l}"),
                    self.progress_var.set(f"[{n}/{t}]"),
                    self._switch_tab(l),
                ))
                self._run_single(label, cmd)
            self._running = False
            self.after(0, lambda: (self.status_var.set("ready"), self.progress_var.set("")))

        threading.Thread(target=run, daemon=True).start()

    def _execute_parallel(self, commands: list[tuple[str, str]]):
        if self._running:
            self._append_line("Already running. Stop first.", "warn")
            return
        self._running        = True
        self._stop_requested = False

        labels = [label for label, _ in commands]
        self.after(0, lambda: self._init_run_buffers(labels))
        self.after(0, lambda: self.status_var.set(f"running parallel ({len(commands)} cmds)"))

        def run():
            threads = []
            for label, cmd in commands:
                t = threading.Thread(target=self._run_single,
                                     args=(label, cmd), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            self._running = False
            self.after(0, lambda: (self.status_var.set("ready"), self.progress_var.set("")))

        threading.Thread(target=run, daemon=True).start()

    def _run_single(self, label: str, cmd: str):
        """Execute one command, stream output into its tab buffer."""
        resolved = resolve_alias(cmd)

        self.after(0, lambda: self._tab_log(
            label, f"┌─ {label} ─────────────────────────────", "header"))
        self.after(0, lambda: self._tab_log(label, f"$ {cmd}", "warn"))

        try:
            proc = subprocess.Popen(
                ["bash", "-c", resolved],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout:
                if self._stop_requested:
                    proc.terminate()
                    break
                self.after(0, lambda l=line.rstrip(): self._tab_log(label, l, "stdout"))
            proc.wait()
            ec = proc.returncode
            if ec == 0:
                self.after(0, lambda: self._tab_log(label, "└─ exit 0 ✓", "success"))
            else:
                self.after(0, lambda c=ec: self._tab_log(label, f"└─ exit {c} ✗", "error"))
        except Exception as ex:
            self.after(0, lambda e=str(ex): self._tab_log(label, f"└─ ERROR: {e}", "error"))

    # ── FILE I/O ──────────────────────────────────────────────────────────────

    def _pick_playbooks_folder(self):
        folder = filedialog.askdirectory(
            title="Select Playbooks Folder",
            initialdir=os.path.expanduser("~"),
        )
        if not folder:
            return
        global PLAYBOOKS_DIR
        PLAYBOOKS_DIR = folder
        self._append_line(f"Playbooks folder set → {folder}", "success")
        self.status_var.set(f"folder: {folder}")

    def _export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".exeflow",
            filetypes=[("ExeFlow Playbook", "*.exeflow"),
                       ("JSON", "*.json"), ("All", "*.*")],
            initialdir=PLAYBOOKS_DIR or os.path.expanduser("~"),
            initialfile=self.playbook.name.replace(" ", "_"),
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump(self.playbook.to_dict(), f, indent=2)
            self._append_line(f"Playbook saved → {path}", "success")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _import(self):
        path = filedialog.askopenfilename(
            initialdir=PLAYBOOKS_DIR or os.path.expanduser("~"),
            filetypes=[("ExeFlow Playbook", "*.exeflow"),
                       ("JSON", "*.json"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.playbook = Playbook.from_dict(data)
            self.pb_name_var.set(self.playbook.name)
            self._checked.clear()
            self._select_all_var.set(False)
            self._refresh_all()
            self._append_line(f"Playbook imported ← {path}", "success")
        except Exception as e:
            messagebox.showerror("Import Error", str(e))


# ──────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ExeFlow()
    app.mainloop()
