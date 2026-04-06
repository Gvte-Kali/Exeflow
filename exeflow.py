#!/usr/bin/env python3
"""
ExeFlow — Command Orchestrator for Exegol
A variable-driven, shareable command sequencer built for pentesters.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import threading
import json
import os
import re
from datetime import datetime

# ──────────────────────────────────────────────
#  PATHS
# ──────────────────────────────────────────────
PLAYBOOKS_DIR = None

# ──────────────────────────────────────────────
#  THEME
# ──────────────────────────────────────────────
BG        = "#0d0f0e"
BG2       = "#131614"
BG3       = "#1a1d1b"
BG4       = "#222624"
BORDER    = "#2a2e2b"
GREEN     = "#39ff7e"
GREEN_DIM = "#1e7a42"
GREEN_MUT = "#2a4a35"
AMBER     = "#ffb347"
RED       = "#ff4f4f"
CYAN      = "#4fc3f7"
WHITE     = "#e8ede9"
GRAY      = "#6b7570"
FONT_MONO    = ("Monospace", 10)
FONT_MONO_SM = ("Monospace", 9)
FONT_TITLE   = ("Monospace", 14, "bold")

# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────

def resolve_command(cmd_template: str, variables: dict) -> str:
    def replacer(m):
        key = m.group(1).strip()
        return variables.get(key, m.group(0))
    return re.sub(r'\{\{([^}]+)\}\}', replacer, cmd_template)

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

# ──────────────────────────────────────────────
#  DATA MODELS
# ──────────────────────────────────────────────

class Variable:
    def __init__(self, name="", value="", description=""):
        self.name        = name
        self.value       = value
        self.description = description

    def to_dict(self):
        return {"name": self.name, "value": self.value, "description": self.description}

    @staticmethod
    def from_dict(d):
        return Variable(d.get("name",""), d.get("value",""), d.get("description",""))


class Command:
    def __init__(self, label="", template="", description="", enabled=True):
        self.label       = label
        self.template    = template
        self.description = description
        self.enabled     = enabled

    def to_dict(self):
        return {"label": self.label, "template": self.template,
                "description": self.description, "enabled": self.enabled}

    @staticmethod
    def from_dict(d):
        return Command(d.get("label",""), d.get("template",""),
                       d.get("description",""), d.get("enabled", True))


class Playbook:
    def __init__(self, name="Unnamed Playbook", description=""):
        self.name        = name
        self.description = description
        self.variables: list[Variable] = []
        self.commands:  list[Command]  = []

    def to_dict(self):
        return {"name": self.name, "description": self.description,
                "variables": [v.to_dict() for v in self.variables],
                "commands":  [c.to_dict() for c in self.commands]}

    @staticmethod
    def from_dict(d):
        pb = Playbook(d.get("name","Unnamed"), d.get("description",""))
        pb.variables = [Variable.from_dict(v) for v in d.get("variables", [])]
        pb.commands  = [Command.from_dict(c)  for c in d.get("commands",  [])]
        return pb

    def get_vars_dict(self):
        return {v.name: v.value for v in self.variables}

# ──────────────────────────────────────────────
#  STYLED WIDGETS
# ──────────────────────────────────────────────

def styled_btn(parent, text, command=None, color=GREEN, width=None, **kw):
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

def separator(parent, color=BORDER, pady=4):
    f = tk.Frame(parent, bg=color, height=1)
    f.pack(fill="x", padx=8, pady=pady)
    return f

def section_label(parent, text, color=GREEN):
    f = tk.Frame(parent, bg=BG)
    f.pack(fill="x", padx=8, pady=(8, 2))
    tk.Label(f, text=text, bg=BG, fg=color, font=FONT_MONO_SM).pack(side="left")
    tk.Frame(f, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(6, 0))
    return f

# ──────────────────────────────────────────────
#  VARIABLE EDITOR DIALOG
# ──────────────────────────────────────────────

class VarDialog(tk.Toplevel):
    def __init__(self, parent, variable: Variable = None):
        super().__init__(parent)
        self.result = None
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
            e = tk.Entry(self, bg=BG3, fg=WHITE, insertbackground=GREEN, font=FONT_MONO,
                         relief="flat", bd=0, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=GREEN)
            e.insert(0, getattr(var, attr))
            e.pack(fill="x", padx=12, pady=(0, 6))
            setattr(self, f"e_{attr}", e)

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
            messagebox.showerror("Error", "Variable name required", parent=self); return
        if not re.match(r'^[A-Za-z0-9_]+$', name):
            messagebox.showerror("Error", "Name: alphanumeric + underscore only", parent=self); return
        self.result = Variable(name, self.e_value.get(), self.e_description.get())
        self.destroy()

# ──────────────────────────────────────────────
#  COMMAND EDITOR DIALOG
# ──────────────────────────────────────────────

class CmdDialog(tk.Toplevel):
    def __init__(self, parent, command: Command = None, variables: list = None):
        super().__init__(parent)
        self.result = None
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
            e = tk.Entry(self, bg=BG3, fg=WHITE, insertbackground=GREEN, font=FONT_MONO,
                         relief="flat", bd=0, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=CYAN)
            e.insert(0, getattr(cmd, attr))
            e.pack(fill="x", padx=12, pady=(0, 6))
            setattr(self, f"e_{attr}", e)

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
                def insert_var(t=tag):
                    self.e_template.insert("insert", t)
                    self.e_template.focus_set()
                styled_btn(vf, v.name, insert_var, color=AMBER, pady=2).pack(side="left", padx=(0, 4))

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12, pady=(0, 12))
        styled_btn(row, "✓ Save",   self._save,   color=CYAN).pack(side="right", padx=4)
        styled_btn(row, "✗ Cancel", self.destroy, color=GRAY).pack(side="right")
        self.e_label.focus_set()

    def _save(self):
        label    = self.e_label.get().strip()
        template = self.e_template.get("1.0", "end-1c").strip()
        if not label:
            messagebox.showerror("Error", "Label required", parent=self); return
        if not template:
            messagebox.showerror("Error", "Command template required", parent=self); return
        self.result = Command(label, template, self.e_description.get().strip())
        self.destroy()

# ──────────────────────────────────────────────
#  MAIN APP
# ──────────────────────────────────────────────

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
        # checked state stored by command index: {idx: bool}
        self._checked: dict[int, bool] = {}

        self._build_ui()
        self._refresh_all()

    # ── UI BUILD ─────────────────────────────

    def _build_ui(self):
        # TOP BAR
        topbar = tk.Frame(self, bg=BG2, height=44)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="⬡ EXEFLOW", bg=BG2, fg=GREEN,
                 font=FONT_TITLE, padx=16).pack(side="left", pady=6)
        tk.Label(topbar, text="command orchestrator", bg=BG2, fg=GREEN_DIM,
                 font=FONT_MONO_SM).pack(side="left")
        tk.Label(topbar, text="│", bg=BG2, fg=BORDER,
                 font=("Monospace", 14, "bold")).pack(side="left", padx=8)

        self.pb_name_var = tk.StringVar(value=self.playbook.name)
        name_entry = tk.Entry(topbar, textvariable=self.pb_name_var, bg=BG2, fg=AMBER,
                              insertbackground=AMBER, font=("Monospace", 11, "bold"),
                              relief="flat", bd=0, width=30)
        name_entry.pack(side="left")
        name_entry.bind("<FocusOut>", lambda e: setattr(self.playbook, "name", self.pb_name_var.get()))

        for text, cmd, color in [
            ("⬇ Export",           self._export,                WHITE),
            ("⬆ Import",           self._import,                WHITE),
            ("📁 Playbooks Folder", self._pick_playbooks_folder, WHITE),
        ]:
            styled_btn(topbar, text, cmd, color=color).pack(side="right", padx=3, pady=6)

        # STATUS BAR
        self.status_bar = tk.Frame(self, bg=BG2, height=24)
        self.status_bar.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="ready")
        tk.Label(self.status_bar, textvariable=self.status_var,
                 bg=BG2, fg=GREEN_DIM, font=FONT_MONO_SM, padx=8).pack(side="left")
        self.progress_var = tk.StringVar(value="")
        tk.Label(self.status_bar, textvariable=self.progress_var,
                 bg=BG2, fg=AMBER, font=FONT_MONO_SM, padx=8).pack(side="right")

        # MAIN PANES
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
        total = self._paned.winfo_width()
        if total > 10:
            self._paned.sash_place(0, total // 2, 0)
        else:
            self.after(100, self._set_sash_center)

    # ── LEFT PANEL ───────────────────────────

    def _build_left(self, parent):
        # VARIABLES
        section_label(parent, "[ VARIABLES ]", GREEN)

        var_toolbar = tk.Frame(parent, bg=BG)
        var_toolbar.pack(fill="x", padx=8, pady=(0, 4))
        styled_btn(var_toolbar, "+ Add",  self._add_variable,  color=GREEN, pady=2).pack(side="left")
        styled_btn(var_toolbar, "✎ Edit", self._edit_variable, color=WHITE, pady=2).pack(side="left", padx=4)
        styled_btn(var_toolbar, "✗ Del",  self._del_variable,  color=RED,   pady=2).pack(side="left")

        vf = tk.Frame(parent, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        vf.pack(fill="x", padx=8, pady=(0, 4))

        self.var_tree = ttk.Treeview(vf, columns=("Name","Value","Desc"),
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

        # COMMANDS
        section_label(parent, "[ COMMANDS ]", CYAN)

        cmd_toolbar = tk.Frame(parent, bg=BG)
        cmd_toolbar.pack(fill="x", padx=8, pady=(0, 2))
        styled_btn(cmd_toolbar, "+ Add",  self._add_command,  color=CYAN,  pady=2).pack(side="left")
        styled_btn(cmd_toolbar, "✎ Edit", self._edit_command, color=WHITE, pady=2).pack(side="left", padx=4)
        styled_btn(cmd_toolbar, "✗ Del",  self._del_command,  color=RED,   pady=2).pack(side="left")
        styled_btn(cmd_toolbar, "↑", self._cmd_up,   color=WHITE, pady=2, width=2).pack(side="left", padx=(8,2))
        styled_btn(cmd_toolbar, "↓", self._cmd_down, color=WHITE, pady=2, width=2).pack(side="left")

        # Select-all row
        sel_row = tk.Frame(parent, bg=BG)
        sel_row.pack(fill="x", padx=8, pady=(2, 2))
        self._select_all_var = tk.BooleanVar(value=False)
        tk.Checkbutton(sel_row, text="Select / Deselect All",
                       variable=self._select_all_var,
                       command=self._toggle_select_all,
                       bg=BG, fg=WHITE, selectcolor=BG3,
                       activebackground=BG, font=FONT_MONO_SM).pack(side="left")

        # ── Command list via Treeview (reliable on all Tkinter versions)
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

        self.cmd_tree.bind("<Button-1>",     self._on_cmd_click)
        self.cmd_tree.bind("<Double-Button-1>", self._on_cmd_double_click)
        self.cmd_tree.tag_configure("checked",   foreground=GREEN)
        self.cmd_tree.tag_configure("unchecked", foreground=WHITE)
        self.cmd_tree.tag_configure("disabled",  foreground=GRAY)

    # ── RIGHT PANEL ──────────────────────────

    def _build_right(self, parent):
        section_label(parent, "[ OUTPUT ]", GREEN)

        out_toolbar = tk.Frame(parent, bg=BG)
        out_toolbar.pack(fill="x", padx=8, pady=(0, 4))

        styled_btn(out_toolbar, "▶ Run Checked",   self._run_checked,  color=GREEN, pady=2).pack(side="left")
        styled_btn(out_toolbar, "▶▶ Run All",       self._run_all,      color=GREEN, pady=2).pack(side="left", padx=4)
        styled_btn(out_toolbar, "⟳ Run Parallel",   self._run_parallel, color=AMBER, pady=2).pack(side="left")
        styled_btn(out_toolbar, "■ Stop",            self._stop,         color=RED,   pady=2).pack(side="left", padx=4)

        tk.Frame(out_toolbar, bg=BORDER, width=1).pack(side="left", fill="y", padx=6, pady=2)

        styled_btn(out_toolbar, "💾 Save Output", self._save_output,  color=CYAN,  pady=2).pack(side="left")
        styled_btn(out_toolbar, "⌫ Clear",        self._clear_output, color=WHITE, pady=2).pack(side="left", padx=4)

        self.autoscroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(out_toolbar, text="Auto-scroll", variable=self.autoscroll_var,
                       bg=BG, fg=WHITE, selectcolor=BG3, activebackground=BG,
                       font=FONT_MONO_SM).pack(side="left", padx=(6,0))

        self.timestamp_var = tk.BooleanVar(value=True)
        tk.Checkbutton(out_toolbar, text="Timestamps", variable=self.timestamp_var,
                       bg=BG, fg=WHITE, selectcolor=BG3, activebackground=BG,
                       font=FONT_MONO_SM).pack(side="left", padx=4)

        term_frame = tk.Frame(parent, bg=BG2, highlightthickness=1, highlightbackground=BORDER)
        term_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.output = tk.Text(term_frame, bg=BG2, fg=GREEN, font=FONT_MONO_SM,
                              insertbackground=GREEN, relief="flat", bd=6,
                              state="disabled", wrap="none")
        ysb = ttk.Scrollbar(term_frame, orient="vertical",   command=self.output.yview)
        xsb = ttk.Scrollbar(term_frame, orient="horizontal", command=self.output.xview)
        self.output.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        xsb.pack(side="bottom", fill="x")
        ysb.pack(side="right",  fill="y")
        self.output.pack(fill="both", expand=True)

        self.output.tag_configure("header",  foreground=CYAN,  font=("Monospace", 10, "bold"))
        self.output.tag_configure("success", foreground=GREEN)
        self.output.tag_configure("error",   foreground=RED)
        self.output.tag_configure("warn",    foreground=AMBER)
        self.output.tag_configure("dim",     foreground=GRAY)
        self.output.tag_configure("stdout",  foreground=WHITE)

        self._apply_ttk_style()

    def _apply_ttk_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background=BG3, foreground=WHITE, fieldbackground=BG3,
                        borderwidth=0, rowheight=24, font=FONT_MONO_SM)
        style.configure("Treeview.Heading",
                        background=BG4, foreground=GRAY, borderwidth=0, font=FONT_MONO_SM)
        style.map("Treeview",
                  background=[("selected", BG4)],
                  foreground=[("selected", WHITE)])
        style.configure("Vertical.TScrollbar",
                        background=BG3, troughcolor=BG2, borderwidth=0, arrowsize=12)
        style.configure("Horizontal.TScrollbar",
                        background=BG3, troughcolor=BG2, borderwidth=0, arrowsize=12)

    def _style_tree(self, tree):
        tree.tag_configure("disabled", foreground=GRAY)
        tree.tag_configure("enabled",  foreground=WHITE)

    # ── REFRESH ──────────────────────────────

    def _refresh_all(self):
        self._refresh_vars()
        self._refresh_cmds()

    def _refresh_vars(self):
        self.var_tree.delete(*self.var_tree.get_children())
        for v in self.playbook.variables:
            self.var_tree.insert("", "end", values=(v.name, v.value, v.description))

    def _refresh_cmds(self):
        # Preserve checked state by label before rebuild
        old_checked = {}
        for iid in self.cmd_tree.get_children():
            vals = self.cmd_tree.item(iid, "values")
            label = vals[1] if len(vals) > 1 else ""
            old_checked[label] = (vals[0] == "☑")

        self.cmd_tree.delete(*self.cmd_tree.get_children())
        self._checked.clear()

        vars_dict = self.playbook.get_vars_dict()

        for i, cmd in enumerate(self.playbook.commands):
            is_checked = old_checked.get(cmd.label, False)
            self._checked[i] = is_checked

            chk_icon = "☑" if is_checked else "☐"
            preview  = resolve_command(cmd.template, vars_dict)
            short    = preview[:60] + "…" if len(preview) > 60 else preview

            tag = "checked" if is_checked else ("disabled" if not cmd.enabled else "unchecked")
            self.cmd_tree.insert("", "end", iid=str(i),
                                 values=(chk_icon, cmd.label, short),
                                 tags=(tag,))

    # ── CHECKBOX INTERACTIONS ────────────────

    def _on_cmd_click(self, event):
        """Toggle checkbox on click. If parallel running, also switch output view."""
        region = self.cmd_tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return
        iid = self.cmd_tree.identify_row(event.y)
        if not iid:
            return
        idx = int(iid)

        # If parallel mode is active, clicking switches the output view
        if hasattr(self, "_parallel_buffers") and self._running:
            label = self.playbook.commands[idx].label
            if label in self._parallel_buffers:
                self._parallel_active_label = label
                self._refresh_parallel_output()
                self.status_var.set(f"viewing: {label}")
                return

        self._checked[idx] = not self._checked.get(idx, False)
        self._update_cmd_row(idx)

    def _on_cmd_double_click(self, event):
        iid = self.cmd_tree.identify_row(event.y)
        if iid:
            self._edit_command_by_idx(int(iid))

    def _update_cmd_row(self, idx):
        if idx >= len(self.playbook.commands):
            return
        cmd       = self.playbook.commands[idx]
        is_checked = self._checked.get(idx, False)
        chk_icon  = "☑" if is_checked else "☐"
        vars_dict = self.playbook.get_vars_dict()
        preview   = resolve_command(cmd.template, vars_dict)
        short     = preview[:60] + "…" if len(preview) > 60 else preview
        tag = "checked" if is_checked else ("disabled" if not cmd.enabled else "unchecked")
        self.cmd_tree.item(str(idx), values=(chk_icon, cmd.label, short), tags=(tag,))

    def _toggle_select_all(self):
        val = self._select_all_var.get()
        for idx in range(len(self.playbook.commands)):
            self._checked[idx] = val
            self._update_cmd_row(idx)

    def _get_checked_indices(self) -> list[int]:
        return [i for i, v in self._checked.items() if v]

    # ── OUTPUT ───────────────────────────────

    def _log(self, text, tag="stdout", newline=True):
        self.output.config(state="normal")
        if self.timestamp_var.get() and tag in ("header", "warn", "error"):
            self.output.insert("end", f"[{get_timestamp()}] ", "dim")
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
            initialfile=f"exeflow_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        if not path:
            return
        try:
            content = self.output.get("1.0", "end-1c")
            with open(path, "w") as f:
                f.write(content)
            self._log(f"Output saved → {path}", "success")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    # ── VARIABLE ACTIONS ─────────────────────

    def _add_variable(self):
        dlg = VarDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            if dlg.result.name in [v.name for v in self.playbook.variables]:
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

    def _get_selected_var_idx(self):
        sel = self.var_tree.selection()
        if not sel:
            return None
        return list(self.var_tree.get_children()).index(sel[0])

    # ── COMMAND ACTIONS ──────────────────────

    def _add_command(self):
        dlg = CmdDialog(self, variables=self.playbook.variables)
        self.wait_window(dlg)
        if dlg.result:
            self.playbook.commands.append(dlg.result)
            self._refresh_cmds()

    def _edit_command(self):
        checked = self._get_checked_indices()
        if not checked:
            # fallback: use treeview selection
            sel = self.cmd_tree.selection()
            if sel:
                self._edit_command_by_idx(int(sel[0]))
            else:
                messagebox.showinfo("Edit Command", "Click a command row to select it, then press Edit.")
            return
        self._edit_command_by_idx(checked[0])

    def _edit_command_by_idx(self, idx):
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
        cmds = self.playbook.commands
        cmds[idx-1], cmds[idx] = cmds[idx], cmds[idx-1]
        self._checked[idx-1], self._checked[idx] = self._checked.get(idx, False), self._checked.get(idx-1, False)
        self._refresh_cmds()

    def _cmd_down(self):
        checked = self._get_checked_indices()
        if not checked or checked[-1] >= len(self.playbook.commands) - 1:
            return
        idx = checked[-1]
        cmds = self.playbook.commands
        cmds[idx+1], cmds[idx] = cmds[idx], cmds[idx+1]
        self._checked[idx+1], self._checked[idx] = self._checked.get(idx, False), self._checked.get(idx+1, False)
        self._refresh_cmds()

    # ── EXECUTION ────────────────────────────

    def _run_checked(self):
        checked = self._get_checked_indices()
        if not checked:
            self._log("No commands checked. Check at least one.", "warn")
            return
        cmds = [(self.playbook.commands[i].label,
                 resolve_command(self.playbook.commands[i].template, self.playbook.get_vars_dict()))
                for i in checked]
        self._execute_sequential(cmds)

    def _run_all(self):
        cmds = [(c.label, resolve_command(c.template, self.playbook.get_vars_dict()))
                for c in self.playbook.commands]
        if not cmds:
            self._log("No commands in playbook.", "warn")
            return
        self._execute_sequential(cmds)

    def _run_parallel(self):
        checked = self._get_checked_indices()
        if not checked:
            self._log("No commands checked for parallel run. Check at least one.", "warn")
            return
        cmds = [(self.playbook.commands[i].label,
                 resolve_command(self.playbook.commands[i].template, self.playbook.get_vars_dict()))
                for i in checked]
        self._execute_parallel(cmds)

    def _stop(self):
        self._stop_requested = True
        self._log("── Stop requested ──", "warn")

    def _execute_sequential(self, commands: list[tuple]):
        if self._running:
            self._log("Already running. Stop first.", "warn")
            return
        self._running        = True
        self._stop_requested = False

        def run():
            total = len(commands)
            for i, (label, cmd) in enumerate(commands):
                if self._stop_requested:
                    self.after(0, lambda: self._log("── Stopped by user ──", "warn"))
                    break
                self.after(0, lambda l=label, n=i+1, t=total: [
                    self.status_var.set(f"running: {l}"),
                    self.progress_var.set(f"[{n}/{t}]")
                ])
                self._run_single(label, cmd)

            self._running = False
            self.after(0, lambda: [self.status_var.set("ready"), self.progress_var.set("")])

        threading.Thread(target=run, daemon=True).start()

    def _execute_parallel(self, commands: list[tuple]):
        if self._running:
            self._log("Already running. Stop first.", "warn")
            return
        self._running        = True
        self._stop_requested = False

        # Per-command output buffer  {label: [(text, tag), ...]}
        self._parallel_buffers: dict[str, list] = {label: [] for label, _ in commands}
        self._parallel_labels: list[str]         = [label for label, _ in commands]
        self._parallel_active_label: str | None  = self._parallel_labels[0] if commands else None

        self.after(0, self._refresh_parallel_output)
        self.after(0, lambda: self.status_var.set(f"running parallel ({len(commands)} cmds)"))

        def buf_log(label, text, tag="stdout"):
            self._parallel_buffers[label].append((text, tag))
            # Refresh display if this label is currently selected
            if self._parallel_active_label == label:
                self.after(0, self._refresh_parallel_output)

        def run():
            threads = []
            for label, cmd in commands:
                log_fn = lambda t, tg="stdout", l=label: buf_log(l, t, tg)
                t = threading.Thread(target=self._run_single,
                                     args=(label, cmd, log_fn), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            self._running = False
            self.after(0, lambda: [self.status_var.set("ready"), self.progress_var.set("")])

        threading.Thread(target=run, daemon=True).start()

    def _refresh_parallel_output(self):
        """Redraw the output terminal with the buffer of the currently selected parallel command."""
        label = getattr(self, "_parallel_active_label", None)
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
        """Run one command via login shell and stream output. Called from worker threads."""
        log = log_fn or self._log
        self.after(0, lambda: log(
            f"┌─ {label} ─────────────────────────────", "header"))
        self.after(0, lambda: log(f"$ {cmd}", "warn"))
        try:
            # Run via plain bash (no --login, no -i) to avoid:
            # - job control errors (no TTY)
            # - /opt/.exegol_aliases syntax error triggered by --login
            # RVM and wrappers are sourced manually and safely.
            wrapper = (
                # RVM: add to PATH and source scripts
                'export PATH="/usr/local/rvm/bin:$PATH"; '
                '[ -s /usr/local/rvm/scripts/rvm ] && source /usr/local/rvm/scripts/rvm 2>/dev/null; '
                # Activate all gem wrappers by scanning rvm gems dirs
                'for d in /usr/local/rvm/gems/*/wrappers; do export PATH="$d:$PATH"; done; '
                'for d in /usr/local/rvm/gems/*/bin; do export PATH="$d:$PATH"; done; '
                'for d in /usr/local/rvm/rubies/*/bin; do export PATH="$d:$PATH"; done; '
                # Standard system paths
                'export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"; '
                # Exegol tools
                'export PATH="/opt/tools/bin:/opt/tools:$PATH"; '
                f'{cmd}'
            )
            proc = subprocess.Popen(
                ["bash", "-c", wrapper],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
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

    # ── FILE I/O ─────────────────────────────

    def _pick_playbooks_folder(self):
        folder = filedialog.askdirectory(
            title="Select Playbooks Folder",
            initialdir=os.path.expanduser("~")
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
            filetypes=[("ExeFlow Playbook", "*.exeflow"), ("JSON", "*.json"), ("All", "*.*")],
            initialdir=PLAYBOOKS_DIR or os.path.expanduser("~"),
            initialfile=self.playbook.name.replace(" ", "_")
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
            filetypes=[("ExeFlow Playbook", "*.exeflow"), ("JSON", "*.json"), ("All", "*.*")]
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

# ──────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app = ExeFlow()
    app.mainloop()
