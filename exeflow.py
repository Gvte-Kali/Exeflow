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
PLAYBOOKS_DIR = None  # Set by user at runtime via "📁 Playbooks Folder" button

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

        self.playbook         = Playbook("New Playbook")
        self._running         = False
        self._stop_requested  = False
        self._check_vars: dict[int, tk.BooleanVar] = {}
        self._select_all_var  = tk.BooleanVar(value=False)

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

        # Right-side buttons (packed right-to-left)
        for text, cmd, color in [
            ("⬇ Export",            self._export,                WHITE),
            ("⬆ Import",            self._import,                WHITE),
            ("📁 Playbooks Folder",  self._pick_playbooks_folder, WHITE),
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

        # MAIN PANES — 50/50 enforced after draw
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

        cols = ("Name", "Value", "Desc")
        self.var_tree = ttk.Treeview(vf, columns=cols, show="headings",
                                     height=8, selectmode="browse")
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
        styled_btn(cmd_toolbar, "+ Add",  self._add_command,  color=CYAN, pady=2).pack(side="left")
        styled_btn(cmd_toolbar, "✎ Edit", self._edit_command, color=WHITE, pady=2).pack(side="left", padx=4)
        styled_btn(cmd_toolbar, "✗ Del",  self._del_command,  color=RED,  pady=2).pack(side="left")
        styled_btn(cmd_toolbar, "↑", self._cmd_up,   color=WHITE, pady=2, width=2).pack(side="left", padx=(8, 2))
        styled_btn(cmd_toolbar, "↓", self._cmd_down, color=WHITE, pady=2, width=2).pack(side="left")

        # Select-all row
        sel_row = tk.Frame(parent, bg=BG)
        sel_row.pack(fill="x", padx=8, pady=(0, 4))
        tk.Checkbutton(sel_row, text="Select / Deselect All",
                       variable=self._select_all_var,
                       command=self._toggle_select_all,
                       bg=BG, fg=WHITE, selectcolor=BG3,
                       activebackground=BG, font=FONT_MONO_SM).pack(side="left")

        # Scrollable command list
        cf_outer = tk.Frame(parent, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        cf_outer.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self._cmd_canvas = tk.Canvas(cf_outer, bg=BG3, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(cf_outer, orient="vertical", command=self._cmd_canvas.yview)
        self._cmd_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._cmd_canvas.pack(side="left", fill="both", expand=True)

        self._cmd_list_frame = tk.Frame(self._cmd_canvas, bg=BG3)
        self._cmd_canvas_window = self._cmd_canvas.create_window(
            (0, 0), window=self._cmd_list_frame, anchor="nw"
        )
        self._cmd_list_frame.bind("<Configure>", lambda e: self._cmd_canvas.configure(
            scrollregion=self._cmd_canvas.bbox("all")))
        self._cmd_canvas.bind("<Configure>", lambda e: self._cmd_canvas.itemconfig(
            self._cmd_canvas_window, width=e.width))

        # Mousewheel
        for widget in (self._cmd_canvas, self._cmd_list_frame):
            widget.bind("<Button-4>",   lambda e: self._cmd_canvas.yview_scroll(-1, "units"))
            widget.bind("<Button-5>",   lambda e: self._cmd_canvas.yview_scroll(1,  "units"))
            widget.bind("<MouseWheel>", lambda e: self._cmd_canvas.yview_scroll(
                int(-1 * e.delta / 120), "units"))

    # ── RIGHT PANEL ──────────────────────────

    def _build_right(self, parent):
        section_label(parent, "[ OUTPUT ]", GREEN)

        out_toolbar = tk.Frame(parent, bg=BG)
        out_toolbar.pack(fill="x", padx=8, pady=(0, 4))

        # Run controls
        styled_btn(out_toolbar, "▶ Run Checked", self._run_checked, color=GREEN, pady=2).pack(side="left")
        styled_btn(out_toolbar, "▶▶ Run All",    self._run_all,     color=GREEN, pady=2).pack(side="left", padx=4)
        styled_btn(out_toolbar, "■ Stop",         self._stop,        color=RED,   pady=2).pack(side="left")

        tk.Frame(out_toolbar, bg=BORDER, width=1).pack(side="left", fill="y", padx=8, pady=2)

        # Output controls
        styled_btn(out_toolbar, "💾 Save Output", self._save_output,  color=CYAN,  pady=2).pack(side="left")
        styled_btn(out_toolbar, "⌫ Clear",        self._clear_output, color=WHITE, pady=2).pack(side="left", padx=4)

        self.autoscroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(out_toolbar, text="Auto-scroll", variable=self.autoscroll_var,
                       bg=BG, fg=WHITE, selectcolor=BG3, activebackground=BG,
                       font=FONT_MONO_SM).pack(side="left", padx=(8,0))

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
                        borderwidth=0, rowheight=22, font=FONT_MONO_SM)
        style.configure("Treeview.Heading",
                        background=BG4, foreground=GRAY, borderwidth=0, font=FONT_MONO_SM)
        style.map("Treeview",
                  background=[("selected", GREEN_MUT)],
                  foreground=[("selected", GREEN)])
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
        # Preserve checkbox states by label
        old_checked = {}
        for idx, bvar in self._check_vars.items():
            if idx < len(self.playbook.commands):
                old_checked[self.playbook.commands[idx].label] = bvar.get()

        for w in self._cmd_list_frame.winfo_children():
            w.destroy()
        self._check_vars.clear()

        vars_dict = self.playbook.get_vars_dict()

        for i, cmd in enumerate(self.playbook.commands):
            bvar = tk.BooleanVar(value=old_checked.get(cmd.label, False))
            self._check_vars[i] = bvar

            row = tk.Frame(self._cmd_list_frame, bg=BG3)
            row.pack(fill="x", pady=1)

            cb = tk.Checkbutton(row, variable=bvar, bg=BG3, activebackground=BG3,
                                 selectcolor=BG4, bd=0, highlightthickness=0)
            cb.pack(side="left", padx=(4, 0))

            label_color = WHITE if cmd.enabled else GRAY
            preview = resolve_command(cmd.template, vars_dict)
            short   = preview[:55] + "…" if len(preview) > 55 else preview
            display = f"  {cmd.label}  ─  {short}"

            lbl = tk.Label(row, text=display, bg=BG3, fg=label_color,
                           font=FONT_MONO_SM, anchor="w", cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True)

            lbl.bind("<Button-1>",        lambda e, b=bvar: b.set(not b.get()))
            lbl.bind("<Double-Button-1>", lambda e, idx=i: self._edit_command_by_idx(idx))

            for widget in (row, lbl, cb):
                widget.bind("<Enter>", lambda e, r=row: r.config(bg=BG4))
                widget.bind("<Leave>", lambda e, r=row: r.config(bg=BG3))
                # Forward mousewheel from rows to canvas
                widget.bind("<Button-4>",   lambda e: self._cmd_canvas.yview_scroll(-1, "units"))
                widget.bind("<Button-5>",   lambda e: self._cmd_canvas.yview_scroll(1,  "units"))
                widget.bind("<MouseWheel>", lambda e: self._cmd_canvas.yview_scroll(
                    int(-1 * e.delta / 120), "units"))

        self._cmd_canvas.update_idletasks()
        self._cmd_canvas.configure(scrollregion=self._cmd_canvas.bbox("all"))

    # ── SELECT ALL ───────────────────────────

    def _toggle_select_all(self):
        val = self._select_all_var.get()
        for bvar in self._check_vars.values():
            bvar.set(val)

    def _get_checked_indices(self) -> list[int]:
        return [i for i, bvar in self._check_vars.items() if bvar.get()]

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
            messagebox.showinfo("Edit Command", "Check a command first to edit it.")
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
            self._refresh_cmds()

    def _cmd_up(self):
        checked = self._get_checked_indices()
        if not checked or checked[0] == 0:
            return
        idx = checked[0]
        cmds = self.playbook.commands
        cmds[idx-1], cmds[idx] = cmds[idx], cmds[idx-1]
        self._refresh_cmds()
        if idx-1 in self._check_vars:
            self._check_vars[idx-1].set(True)

    def _cmd_down(self):
        checked = self._get_checked_indices()
        if not checked or checked[-1] >= len(self.playbook.commands) - 1:
            return
        idx = checked[-1]
        cmds = self.playbook.commands
        cmds[idx+1], cmds[idx] = cmds[idx], cmds[idx+1]
        self._refresh_cmds()
        if idx+1 in self._check_vars:
            self._check_vars[idx+1].set(True)

    # ── EXECUTION ────────────────────────────

    def _run_checked(self):
        checked = self._get_checked_indices()
        if not checked:
            self._log("No commands checked. Check at least one.", "warn")
            return
        cmds = [(self.playbook.commands[i].label,
                 resolve_command(self.playbook.commands[i].template, self.playbook.get_vars_dict()))
                for i in checked]
        self._execute_commands(cmds)

    def _run_all(self):
        cmds = [(c.label, resolve_command(c.template, self.playbook.get_vars_dict()))
                for c in self.playbook.commands]
        if not cmds:
            self._log("No commands in playbook.", "warn")
            return
        self._execute_commands(cmds)

    def _stop(self):
        self._stop_requested = True
        self._log("── Stop requested ──", "warn")

    def _execute_commands(self, commands: list[tuple]):
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
                self.after(0, lambda l=label: self._log(
                    f"┌─ {l} ─────────────────────────────", "header"))
                self.after(0, lambda c=cmd: self._log(f"$ {c}", "warn"))

                try:
                    proc = subprocess.Popen(
                        cmd, shell=True, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, bufsize=1
                    )
                    for line in proc.stdout:
                        if self._stop_requested:
                            proc.terminate()
                            break
                        self.after(0, lambda l=line.rstrip(): self._log(l, "stdout"))
                    proc.wait()
                    ec = proc.returncode
                    if ec == 0:
                        self.after(0, lambda: self._log("└─ exit 0 ✓", "success"))
                    else:
                        self.after(0, lambda c=ec: self._log(f"└─ exit {c} ✗", "error"))
                except Exception as ex:
                    self.after(0, lambda e=str(ex): self._log(f"└─ ERROR: {e}", "error"))

            self._running = False
            self.after(0, lambda: [self.status_var.set("ready"), self.progress_var.set("")])

        threading.Thread(target=run, daemon=True).start()

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
