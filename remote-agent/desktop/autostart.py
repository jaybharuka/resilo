from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


def _executable() -> str:
    if getattr(sys, "frozen", False):
        return str(sys.executable)
    main_py = Path(__file__).parent / "main.py"
    return f'"{sys.executable}" "{main_py}"'


def _setup_windows() -> None:
    startup_dir = (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )
    bat = startup_dir / "resilo_desktop_agent.bat"
    bat.write_text(f'@echo off\nstart "" /B {_executable()}\n')
    print(f"[autostart] Registered: {bat}")


def _setup_mac() -> None:
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist = plist_dir / "com.resilo.desktop_agent.plist"
    exe = _executable()
    plist.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.resilo.desktop_agent</string>
  <key>ProgramArguments</key>
  <array><string>{exe}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>"""
    )
    subprocess.run(["launchctl", "load", str(plist)], check=False)
    print(f"[autostart] Registered: {plist}")


def _setup_linux() -> None:
    svc_dir = Path.home() / ".config" / "systemd" / "user"
    svc_dir.mkdir(parents=True, exist_ok=True)
    svc = svc_dir / "resilo-desktop-agent.service"
    svc.write_text(
        f"""[Unit]
Description=Resilo Desktop Agent

[Service]
ExecStart={_executable()}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""
    )
    for cmd in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "resilo-desktop-agent"],
        ["systemctl", "--user", "start", "resilo-desktop-agent"],
    ):
        subprocess.run(cmd, check=False)
    print(f"[autostart] Registered: {svc}")


def register() -> None:
    system = platform.system()
    if system == "Windows":
        _setup_windows()
    elif system == "Darwin":
        _setup_mac()
    elif system == "Linux":
        _setup_linux()
    else:
        print(f"[autostart] Platform '{system}' not supported — skip")
