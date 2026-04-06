# ⬡ ExeFlow

> **Pentest Command Orchestrator** — Define your variables, build your command sequences, share your workflows. Designed to integrate natively with [Exegol](https://github.com/ThePorgs/Exegol).

## In a nutshell

ExeFlow is a GUI tool that lets you:

- Define **variables** (`TARGET`, `PORT`, `URL`...) reusable across all your commands
- Build **command sequences** that inject those variables automatically via `{{VAR}}` syntax
- Check the commands you want and **run them in one click**, sequentially
- **Save your terminal output** to a text file — useful for long scans you don't want to redo
- **Export** your full variable + command setup into a shareable `.exeflow` file

The idea: stop retyping the same nmap/gobuster/ffuf commands on every engagement. Build your playbook once, share it with your team, reuse it everywhere.

**Zero external dependencies** — Python stdlib + Tkinter only.

---

## Installation

### One-liner

```bash
curl -fsSL https://raw.githubusercontent.com/Gvte-Kali/Exeflow/refs/heads/main/install.sh | sudo bash
```

The installer automatically detects your package manager and installs any missing dependencies (`python3`, `python3-tk`, `curl`).

| Package manager | Distros |
|---|---|
| `apt` | Debian, Ubuntu, Kali, Exegol |
| `pacman` | Arch, BlackArch, Manjaro |
| `dnf` | Fedora, RHEL, CentOS |
| `zypper` | openSUSE |
| `apk` | Alpine |

---

## Launch

```bash
exeflow
```
## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/Gvte-Kali/Exeflow/refs/heads/main/uninstall.sh | sudo bash
```

## Table of contents


- [Interface](#interface)
  - [Top bar](#top-bar)
  - [Variables panel](#variables-panel)
  - [Commands panel](#commands-panel)
  - [Output panel](#output-panel)
- [Variable system](#variable-system)
- [Playbook format](#playbook-format)
- [Exegol integration](#exegol-integration)
- [Sharing playbooks](#sharing-playbooks)
- [Requirements](#requirements)

---


ExeFlow launches detached from the shell — **you get your prompt back immediately**. Logs are written to `/tmp/exeflow.log` if anything goes wrong.

---

## Interface

ExeFlow is split into two equal panels: **left** for your playbook (variables + commands), **right** for the output terminal. The divider is draggable.

### Top bar

| Element | Description |
|---|---|
| Playbook name | Editable inline — click and type |
| `📁 Playbooks Folder` | Set the directory where playbooks are saved and loaded |
| `⬆ Import` | Load a `.exeflow` playbook file |
| `⬇ Export` | Save the current playbook to a `.exeflow` file |

### Variables panel

Variables are named placeholders that get injected into your command templates. You define them once and reuse them across every command.

| Button | Action |
|---|---|
| `+ Add` | Open the variable editor to create a new variable |
| `✎ Edit` | Edit the selected variable (also double-click) |
| `✗ Del` | Delete the selected variable |

Each variable has three fields: **Name** (used as `{{NAME}}` in commands), **Value** (the actual string to inject), and an optional **Description**.

> Changing a variable's value instantly updates the resolved preview of all commands that reference it.

### Commands panel

Commands are shell instructions stored as templates. They reference variables using `{{VAR_NAME}}` syntax.

| Button | Action |
|---|---|
| `+ Add` | Open the command editor |
| `✎ Edit` | Edit the first checked command (also double-click a row) |
| `✗ Del` | Delete all checked commands |
| `↑` / `↓` | Reorder the first checked command |
| `Select / Deselect All` | Toggle all checkboxes at once |

Each command row shows a **checkbox**, its **label**, and a **resolved preview** of the command with variables already substituted. Click anywhere on the row to toggle its checkbox. Double-click to open the editor.

### Output panel

The output panel is a read-only terminal that streams command output in real time.

| Control | Description |
|---|---|
| `▶ Run Checked` | Execute all checked commands sequentially |
| `▶▶ Run All` | Execute every command in the playbook regardless of checkboxes |
| `■ Stop` | Interrupt the running command and halt the sequence |
| `💾 Save Output` | Save the full terminal content to a `.txt` or `.log` file |
| `⌫ Clear` | Clear the terminal |
| `Auto-scroll` | Automatically scroll to the latest output line |
| `Timestamps` | Prefix section headers with `[HH:MM:SS]` |

Output is color-coded: section headers in cyan, commands in amber, stdout in white, `exit 0` in green, non-zero exits in red.

---

## Variable system

Variables are injected using double-brace syntax:

```
{{VARIABLE_NAME}}
```

**Example setup:**

| Name | Value |
|---|---|
| `TARGET` | `10.10.10.10` |
| `PORT` | `443` |
| `DOMAIN` | `target.htb` |
| `WORDLIST` | `/usr/share/wordlists/dirb/common.txt` |

**Example command template:**

```
gobuster dir -u https://{{DOMAIN}}:{{PORT}} -w {{WORDLIST}} -o /tmp/gobuster_{{TARGET}}.txt
```

**Resolved at runtime:**

```
gobuster dir -u https://target.htb:443 -w /usr/share/wordlists/dirb/common.txt -o /tmp/gobuster_10.10.10.10.txt
```

If a variable referenced in a template has no defined value, the placeholder is left as-is so you can spot it immediately.

In the command editor, variable names appear as **quick-insert buttons** — click one to insert the `{{VAR}}` tag at the cursor position.

---

## Playbook format

Playbooks are plain JSON files with a `.exeflow` extension. They are human-readable, easy to diff, and safe to version-control.

```json
{
  "name": "Web Enumeration",
  "description": "",
  "variables": [
    { "name": "TARGET",   "value": "10.10.10.10",                              "description": "Target IP"      },
    { "name": "PORT",     "value": "80",                                        "description": "Target port"    },
    { "name": "DOMAIN",   "value": "target.htb",                               "description": "Domain name"    },
    { "name": "WORDLIST", "value": "/usr/share/wordlists/dirb/common.txt",     "description": "Wordlist path"  }
  ],
  "commands": [
    {
      "label": "Nmap",
      "template": "nmap -sV -sC -p- {{TARGET}} -oN /tmp/nmap_{{TARGET}}.txt",
      "description": "Full port scan",
      "enabled": true
    },
    {
      "label": "Gobuster",
      "template": "gobuster dir -u http://{{DOMAIN}}:{{PORT}} -w {{WORDLIST}}",
      "description": "Directory brute-force",
      "enabled": true
    },
    {
      "label": "WhatWeb",
      "template": "whatweb http://{{DOMAIN}}:{{PORT}}",
      "description": "Tech fingerprinting",
      "enabled": true
    }
  ]
}
```

---

## Exegol integration

ExeFlow runs natively inside any Exegol graphical container (`full` image or any image with `python3-tk`).

### Persistent playbooks across containers

Exegol automatically mounts `~/.exegol/my-resources/` into every container. Store your playbooks there so they are available everywhere without any extra setup:

```
~/.exegol/my-resources/
└── playbooks/
    ├── web_enum.exeflow
    ├── active_directory.exeflow
    ├── network_scan.exeflow
    └── ...
```

On first launch, click `📁 Playbooks Folder` and navigate to `~/.exegol/my-resources/playbooks/`. ExeFlow will use that directory for all imports and exports from that point on.

### Desktop shortcut (optional)

Add ExeFlow to the Exegol graphical application menu:

```bash
cat > ~/.local/share/applications/exeflow.desktop << EOF
[Desktop Entry]
Name=ExeFlow
Comment=Pentest Command Orchestrator
Exec=exeflow
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Security;Network;
EOF
```

---

## Sharing playbooks

Because playbooks are plain JSON, they can be versioned and shared via Git like any other file.

```bash
cd ~/.exegol/my-resources/playbooks/

git init
git remote add origin git@github.com:yourteam/exeflow-playbooks.git

git add .
git commit -m "Add web enumeration playbook"
git push
```

Teammates clone the repo into their own `my-resources/playbooks/` and can use the playbooks immediately — variables included, so they only need to update the values for their target.

---

## Requirements

- Linux (or any Exegol graphical container)
- Python 3.10+
- Tkinter (`python3-tk`)
- A graphical session (`$DISPLAY` or `$WAYLAND_DISPLAY` must be set)

---

## License

MIT — do whatever you want with it.
