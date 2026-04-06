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
#  Converts ANSI escape sequences to Tkinter Text widget tags.
# ──────────────────────────────────────────────────────────────────────────────

ANSI_ESCAPE = re.compile(r"\x1b\[([0-9;]*)m")

ANSI_TAG_MAP = {
    "0":  "ansi_reset",
    "1":  "ansi_bold",
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
    """
    Split a string containing ANSI color codes into (chunk, tag) pairs.
    Returns [(text, tag), ...] where tag is '' for the default color.
    """
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
#  Parses /opt/.exegol_aliases at startup so tools defined as shell aliases
#  (e.g. wpscan, msfconsole, evil-winrm) resolve to their real executables.
# ──────────────────────────────────────────────────────────────────────────────

EXEGOL_ALIASES_PATH = "/opt/.exegol_aliases"


def _load_exegol_aliases(path: str = EXEGOL_ALIASES_PATH) -> dict[str, str]:
    """
    Return {alias_name: real_command} parsed from the Exegol aliases file.
    Handles single-quoted and double-quoted values.
    Skips functions, comments, and blank lines.
    """
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
    """
    If the first token of cmd matches a known Exegol alias, substitute it
    with the real command string. Otherwise return cmd unchanged.

    Example:
        'wpscan --url http://...' → '/usr/local/rvm/.../wpscan --url http://...'
    """
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
    """Replace {{VAR_NAME}} placeholders with their values."""
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
            "name":        self.name,
            "description": self.description,
            "variables":   [v.to_dict() for v in self.variables],
            "commands":    [c.to_dict() for c in self.commands],
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
               cursor="hand2", padx=10, pady=4)
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
            messagebox.showerror("Error", "Variable name required.", parent=self)
            return
        if not re.match(r"^[A-Za-z0-9_]+$", name):
            messagebox.showerror("Error", "Name must be alphanumeric + underscore only.", parent=self)
            return
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
            messagebox.showerror("Error", "Label required.", parent=self)
            return
        if not template:
            messagebox.showerror("Error", "Command template required.", parent=self)
            return
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

        # Parallel mode state
        self._parallel_buffers:      dict[str, list] = {}
        self._parallel_labels:       list[str]       = []
        self._parallel_active_label: str | None      = None

        self._build_ui()
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
                              relief="flat", bd=0, width=30)
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
        self._paned.add(left,  minsize=320)
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
        # Variables section
        section_label(parent, "[ VARIABLES ]", GREEN)

        tb = tk.Frame(parent, bg=BG)
        tb.pack(fill="x", padx=8, pady=(0, 4))
        styled_btn(tb, "+ Add",  self._add_variable,  color=GREEN, pady=2).pack(side="left")
        styled_btn(tb, "✎ Edit", self._edit_variable, color=WHITE, pady=2).pack(side="left", padx=4)
        styled_btn(tb, "✗ Del",  self._del_variable,  color=RED,   pady=2).pack(side="left")

        vf = tk.Frame(parent, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        vf.pack(fill="x", padx=8, pady=(0, 4))

        self.var_tree = ttk.Treeview(vf, columns=("Name", "Value", "Desc"),
                                     show="headings", height=8, selectmode="browse")
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

        # Commands section
        section_label(parent, "[ COMMANDS ]", CYAN)

        tb2 = tk.Frame(parent, bg=BG)
        tb2.pack(fill="x", padx=8, pady=(0, 2))
        styled_btn(tb2, "+ Add",  self._add_command,  color=CYAN,  pady=2).pack(side="left")
        styled_btn(tb2, "✎ Edit", self._edit_command, color=WHITE, pady=2).pack(side="left", padx=4)
        styled_btn(tb2, "✗ Del",  self._del_command,  color=RED,   pady=2).pack(side="left")
        styled_btn(tb2, "↑", self._cmd_up,   color=WHITE, pady=2, width=2).pack(side="left", padx=(8, 2))
        styled_btn(tb2, "↓", self._cmd_down, color=WHITE, pady=2, width=2).pack(side="left")

        sel_row = tk.Frame(parent, bg=BG)
        sel_row.pack(fill="x", padx=8, pady=(2, 2))
        tk.Checkbutton(sel_row, text="Select / Deselect All",
                       variable=self._select_all_var,
                       command=self._toggle_select_all,
                       bg=BG, fg=WHITE, selectcolor=BG3,
                       activebackground=BG, font=FONT_MONO_SM).pack(side="left")

        cf = tk.Frame(parent, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        cf.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self.cmd_tree = ttk.Treeview(cf, columns=("chk", "label", "preview"),
                                     show="headings", selectmode="browse")
        self.cmd_tree.heading("chk",     text="")
        self.cmd_tree.heading("label",   text="LABEL")
        self.cmd_tree.heading("preview", text="COMMAND")
        self.cmd_tree.column("chk",     width=28,  stretch=False, anchor="center")
        self.cmd_tree.column("label",   width=110, stretch=False)
        self.cmd_tree.column("preview", width=200)

        vsb = ttk.Scrollbar(cf, orient="vertical", command=self.cmd_tree.yview)
        self.cmd_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.cmd_tree.pack(fill="both", expand=True)

        self.cmd_tree.bind("<Button-1>",       self._on_cmd_click)
        self.cmd_tree.bind("<Double-Button-1>", self._on_cmd_double_click)
        self.cmd_tree.tag_configure("checked",   foreground=GREEN)
        self.cmd_tree.tag_configure("unchecked", foreground=WHITE)
        self.cmd_tree.tag_configure("disabled",  foreground=GRAY)

    # ── RIGHT PANEL ───────────────────────────────────────────────────────────

    def _build_right(self, parent):
        section_label(parent, "[ OUTPUT ]", GREEN)

        tb = tk.Frame(parent, bg=BG)
        tb.pack(fill="x", padx=8, pady=(0, 4))

        styled_btn(tb, "▶ Run Checked",  self._run_checked,  color=GREEN, pady=2).pack(side="left")
        styled_btn(tb, "▶▶ Run All",      self._run_all,      color=GREEN, pady=2).pack(side="left", padx=4)
        styled_btn(tb, "⟳ Run Parallel",  self._run_parallel, color=AMBER, pady=2).pack(side="left")
        styled_btn(tb, "■ Stop",           self._stop,         color=RED,   pady=2).pack(side="left", padx=4)

        tk.Frame(tb, bg=BORDER, width=1).pack(side="left", fill="y", padx=6, pady=2)

        styled_btn(tb, "💾 Save Output", self._save_output,  color=CYAN,  pady=2).pack(side="left")
        styled_btn(tb, "⌫ Clear",        self._clear_output, color=WHITE, pady=2).pack(side="left", padx=4)

        self.autoscroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(tb, text="Auto-scroll", variable=self.autoscroll_var,
                       bg=BG, fg=WHITE, selectcolor=BG3,
                       activebackground=BG, font=FONT_MONO_SM).pack(side="left", padx=(6, 0))

        self.timestamp_var = tk.BooleanVar(value=True)
        tk.Checkbutton(tb, text="Timestamps", variable=self.timestamp_var,
                       bg=BG, fg=WHITE, selectcolor=BG3,
                       activebackground=BG, font=FONT_MONO_SM).pack(side="left", padx=4)

        term = tk.Frame(parent, bg=BG2, highlightthickness=1, highlightbackground=BORDER)
        term.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.output = tk.Text(term, bg=BG2, fg=GREEN, font=FONT_MONO_SM,
                              insertbackground=GREEN, relief="flat", bd=6,
                              state="disabled", wrap="none")
        ysb = ttk.Scrollbar(term, orient="vertical",   command=self.output.yview)
        xsb = ttk.Scrollbar(term, orient="horizontal", command=self.output.xview)
        self.output.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        xsb.pack(side="bottom", fill="x")
        ysb.pack(side="right",  fill="y")
        self.output.pack(fill="both", expand=True)

        # Standard tags
        self.output.tag_configure("header",  foreground=CYAN, font=("Monospace", 10, "bold"))
        self.output.tag_configure("success", foreground=GREEN)
        self.output.tag_configure("error",   foreground=RED)
        self.output.tag_configure("warn",    foreground=AMBER)
        self.output.tag_configure("dim",     foreground=GRAY)
        self.output.tag_configure("stdout",  foreground=WHITE)

        # ANSI color tags (Dracula-inspired palette)
        ansi_colors = {
            "ansi_reset":          WHITE,
            "ansi_bold":           WHITE,
            "ansi_black":          "#555555",
            "ansi_red":            "#ff5555",
            "ansi_green":          "#50fa7b",
            "ansi_yellow":         "#f1fa8c",
            "ansi_blue":           "#6272a4",
            "ansi_magenta":        "#ff79c6",
            "ansi_cyan":           "#8be9fd",
            "ansi_white":          "#f8f8f2",
            "ansi_bright_black":   "#6272a4",
            "ansi_bright_red":     "#ff6e6e",
            "ansi_bright_green":   "#69ff94",
            "ansi_bright_yellow":  "#ffffa5",
            "ansi_bright_blue":    "#d6acff",
            "ansi_bright_magenta": "#ff92df",
            "ansi_bright_cyan":    "#a4ffff",
            "ansi_bright_white":   "#ffffff",
        }
        for tag, color in ansi_colors.items():
            kw = {"foreground": color}
            if tag == "ansi_bold":
                kw["font"] = ("Monospace", 9, "bold")
            self.output.tag_configure(tag, **kw)

        self._apply_ttk_style()

    def _apply_ttk_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview",
                    background=BG3, foreground=WHITE, fieldbackground=BG3,
                    borderwidth=0, rowheight=24, font=FONT_MONO_SM)
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
        # Preserve checkbox states by label
        old_checked: dict[str, bool] = {}
        for iid in self.cmd_tree.get_children():
            vals = self.cmd_tree.item(iid, "values")
            if len(vals) > 1:
                old_checked[vals[1]] = (vals[0] == "☑")

        self.cmd_tree.delete(*self.cmd_tree.get_children())
        self._checked.clear()
        vd = self.playbook.get_vars_dict()

        for i, cmd in enumerate(self.playbook.commands):
            checked = old_checked.get(cmd.label, False)
            self._checked[i] = checked

            icon    = "☑" if checked else "☐"
            preview = resolve_command(cmd.template, vd)
            short   = (preview[:60] + "…") if len(preview) > 60 else preview
            tag     = "checked" if checked else ("disabled" if not cmd.enabled else "unchecked")

            self.cmd_tree.insert("", "end", iid=str(i),
                                 values=(icon, cmd.label, short), tags=(tag,))

    # ── COMMAND LIST INTERACTIONS ─────────────────────────────────────────────

    def _on_cmd_click(self, event):
        region = self.cmd_tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return
        iid = self.cmd_tree.identify_row(event.y)
        if not iid:
            return
        idx = int(iid)

        # In parallel mode: click switches the output view instead of toggling
        if self._parallel_buffers and self._running:
            label = self.playbook.commands[idx].label
            if label in self._parallel_buffers:
                self._parallel_active_label = label
                self._redraw_parallel_output()
                self.status_var.set(f"viewing: {label}")
                return

        self._checked[idx] = not self._checked.get(idx, False)
        self._update_cmd_row(idx)

    def _on_cmd_double_click(self, event):
        iid = self.cmd_tree.identify_row(event.y)
        if iid:
            self._edit_command_by_idx(int(iid))

    def _update_cmd_row(self, idx: int):
        if idx >= len(self.playbook.commands):
            return
        cmd     = self.playbook.commands[idx]
        checked = self._checked.get(idx, False)
        icon    = "☑" if checked else "☐"
        preview = resolve_command(cmd.template, self.playbook.get_vars_dict())
        short   = (preview[:60] + "…") if len(preview) > 60 else preview
        tag     = "checked" if checked else ("disabled" if not cmd.enabled else "unchecked")
        self.cmd_tree.item(str(idx), values=(icon, cmd.label, short), tags=(tag,))

    def _toggle_select_all(self):
        val = self._select_all_var.get()
        for idx in range(len(self.playbook.commands)):
            self._checked[idx] = val
            self._update_cmd_row(idx)

    def _get_checked_indices(self) -> list[int]:
        return [i for i, v in self._checked.items() if v]

    # ── OUTPUT ────────────────────────────────────────────────────────────────

    def _log(self, text: str, tag: str = "stdout", newline: bool = True):
        self.output.config(state="normal")
        if self.timestamp_var.get() and tag in ("header", "warn", "error"):
            self.output.insert("end", f"[{get_timestamp()}] ", "dim")

        if tag == "stdout" and ANSI_ESCAPE.search(text):
            chunks = parse_ansi(text)
            for i, (chunk, ansi_tag) in enumerate(chunks):
                t = ansi_tag or "stdout"
                suffix = "\n" if (newline and i == len(chunks) - 1) else ""
                self.output.insert("end", chunk + suffix, t)
        else:
            self.output.insert("end", text + ("\n" if newline else ""), tag)

        self.output.config(state="disabled")
        if self.autoscroll_var.get():
            self.output.see("end")

    def _clear_output(self):
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.config(state="disabled")

    def _save_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("Log file", "*.log"), ("All", "*.*")],
            initialdir=PLAYBOOKS_DIR or os.path.expanduser("~"),
            initialfile=f"exeflow_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                f.write(self.output.get("1.0", "end-1c"))
            self._log(f"Output saved → {path}", "success")
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
            sel = self.cmd_tree.selection()
            if sel:
                self._edit_command_by_idx(int(sel[0]))
            else:
                messagebox.showinfo("Edit Command",
                                    "Click a command row to select it, then press Edit.")

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

    def _run_checked(self):
        checked = self._get_checked_indices()
        if not checked:
            self._log("No commands checked. Check at least one.", "warn")
            return
        self._execute_sequential(self._build_cmd_list(checked))

    def _run_all(self):
        if not self.playbook.commands:
            self._log("No commands in playbook.", "warn")
            return
        self._execute_sequential(self._build_cmd_list(range(len(self.playbook.commands))))

    def _run_parallel(self):
        checked = self._get_checked_indices()
        if not checked:
            self._log("No commands checked for parallel run.", "warn")
            return
        self._execute_parallel(self._build_cmd_list(checked))

    def _stop(self):
        self._stop_requested = True
        self._log("── Stop requested ──", "warn")

    def _build_cmd_list(self, indices) -> list[tuple[str, str]]:
        vd = self.playbook.get_vars_dict()
        return [(self.playbook.commands[i].label,
                 resolve_command(self.playbook.commands[i].template, vd))
                for i in indices]

    def _execute_sequential(self, commands: list[tuple[str, str]]):
        if self._running:
            self._log("Already running. Stop first.", "warn")
            return
        self._running        = True
        self._stop_requested = False
        # Clear parallel state so output goes to main terminal
        self._parallel_buffers = {}

        def run():
            total = len(commands)
            for i, (label, cmd) in enumerate(commands):
                if self._stop_requested:
                    self.after(0, lambda: self._log("── Stopped by user ──", "warn"))
                    break
                self.after(0, lambda l=label, n=i + 1, t=total: (
                    self.status_var.set(f"running: {l}"),
                    self.progress_var.set(f"[{n}/{t}]"),
                ))
                self._run_single(label, cmd)
            self._running = False
            self.after(0, lambda: (self.status_var.set("ready"), self.progress_var.set("")))

        threading.Thread(target=run, daemon=True).start()

    def _execute_parallel(self, commands: list[tuple[str, str]]):
        if self._running:
            self._log("Already running. Stop first.", "warn")
            return
        self._running              = True
        self._stop_requested       = False
        self._parallel_buffers     = {label: [] for label, _ in commands}
        self._parallel_labels      = [label for label, _ in commands]
        self._parallel_active_label = self._parallel_labels[0] if commands else None

        self.after(0, self._redraw_parallel_output)
        self.after(0, lambda: self.status_var.set(f"running parallel ({len(commands)} cmds)"))

        def buf_log(label: str, text: str, tag: str = "stdout"):
            self._parallel_buffers[label].append((text, tag))
            if self._parallel_active_label == label:
                self.after(0, self._redraw_parallel_output)

        def run():
            threads = []
            for label, cmd in commands:
                fn = lambda t, tg="stdout", l=label: buf_log(l, t, tg)
                t  = threading.Thread(target=self._run_single,
                                      args=(label, cmd, fn), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            self._running = False
            self.after(0, lambda: (self.status_var.set("ready"), self.progress_var.set("")))

        threading.Thread(target=run, daemon=True).start()

    def _redraw_parallel_output(self):
        label = self._parallel_active_label
        if label is None:
            return
        buf = self._parallel_buffers.get(label, [])
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        for text, tag in buf:
            if self.timestamp_var.get() and tag in ("header", "warn", "error"):
                self.output.insert("end", f"[{get_timestamp()}] ", "dim")
            self.output.insert("end", text + "\n", tag)
        self.output.config(state="disabled")
        if self.autoscroll_var.get():
            self.output.see("end")

    def _run_single(self, label: str, cmd: str, log_fn=None):
        """Execute one command and stream output. Safe to call from worker threads."""
        log = log_fn or self._log
        resolved = resolve_alias(cmd)

        self.after(0, lambda: log(f"┌─ {label} ─────────────────────────────", "header"))
        self.after(0, lambda: log(f"$ {cmd}", "warn"))

        try:
            proc = subprocess.Popen(
                ["bash", "-c", resolved],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                if self._stop_requested:
                    proc.terminate()
                    break
                self.after(0, lambda l=line.rstrip(): log(l, "stdout"))
            proc.wait()
            ec = proc.returncode
            if ec == 0:
                self.after(0, lambda: log("└─ exit 0 ✓", "success"))
            else:
                self.after(0, lambda c=ec: log(f"└─ exit {c} ✗", "error"))
        except Exception as ex:
            self.after(0, lambda e=str(ex): log(f"└─ ERROR: {e}", "error"))

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
        self._log(f"Playbooks folder set → {folder}", "success")
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
            self._log(f"Playbook saved → {path}", "success")
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
            self._log(f"Playbook imported ← {path}", "success")
        except Exception as e:
            messagebox.showerror("Import Error", str(e))


# ──────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ExeFlow()
    app.mainloop()
