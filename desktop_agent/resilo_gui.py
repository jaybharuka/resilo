"""
Resilo Agent — GUI Edition  (self-contained, no external modules needed)
Download ResilioAgent.exe, enter your token, click Connect.
Runs silently in system tray after connecting.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import uuid
from collections import deque
from tkinter import messagebox, scrolledtext
from typing import Any

# ── psutil (bundled by PyInstaller) ──────────────────────────────────────────
try:
    import psutil
except ImportError:
    messagebox.showerror("Missing dependency", "psutil is required.\nRun: pip install psutil")
    sys.exit(1)

# ── Agent logic (inlined — no cross-module import) ────────────────────────────

_BUFFER: deque[dict[str, Any]] = deque(maxlen=50)
_RETRY_DELAYS = (2, 4, 8)
_TASK_NAME    = "ResilioAgent"
_CFG_PATH     = os.path.join(os.path.expanduser("~"), ".resilo_agent.json")


def _disk_root() -> str:
    return "C:\\" if platform.system() == "Windows" else "/"


def _load_avg() -> str | None:
    try:
        avg = psutil.getloadavg()
        return f"{avg[0]:.2f} {avg[1]:.2f} {avg[2]:.2f}"
    except AttributeError:
        return None


def _temperature() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        for key in ("coretemp", "cpu_thermal", "k10temp", "acpitz"):
            if key in temps and temps[key]:
                return round(temps[key][0].current, 1)
        first_key = next(iter(temps))
        if temps[first_key]:
            return round(temps[first_key][0].current, 1)
    except (AttributeError, NotImplementedError):
        pass
    return None


def collect(device_id: str, label: str) -> dict[str, Any]:
    vm   = psutil.virtual_memory()
    disk = psutil.disk_usage(_disk_root())
    net  = psutil.net_io_counters()
    return {
        "cpu": round(psutil.cpu_percent(interval=0.5), 2),
        "memory": round(vm.percent, 2),
        "disk": round(disk.percent, 2),
        "network_in": int(net.bytes_recv),
        "network_out": int(net.bytes_sent),
        "temperature": _temperature(),
        "load_avg": _load_avg(),
        "processes": len(psutil.pids()),
        "uptime_secs": int(time.time() - psutil.boot_time()),
        "extra": {
            "device_id": device_id,
            "agent_label": label,
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "os_version": platform.version(),
            "error_rate": 0,
        },
    }


def _post(url: str, body: dict[str, Any], agent_key: str) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, method="POST", data=data,
        headers={"Content-Type": "application/json", "X-Agent-Key": agent_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read().decode()
            return resp.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed
    except Exception as exc:
        return 0, {"error": str(exc)}


def send(backend_url: str, org_id: str, agent_key: str,
         metrics: dict[str, Any]) -> tuple[bool, float]:
    url  = f"{backend_url.rstrip('/')}/ingest/heartbeat"
    body = {"org_id": org_id, "metrics": metrics}
    while _BUFFER:
        buffered = _BUFFER[0]
        for delay in _RETRY_DELAYS:
            status, _ = _post(url, buffered, agent_key)
            if status == 200:
                _BUFFER.popleft()
                break
            time.sleep(delay)
        else:
            break
    for delay in (*_RETRY_DELAYS, None):
        status, resp = _post(url, body, agent_key)
        if status == 200:
            return True, float(resp.get("poll_interval", 5))
        if delay is None:
            break
        time.sleep(delay)
    _BUFFER.append(body)
    return False, 5.0


def _poll_commands(backend_url: str, agent_key: str) -> list[dict[str, Any]]:
    url = f"{backend_url.rstrip('/')}/agent/command?token={agent_key}"
    req = urllib.request.Request(url, method="GET",
                                 headers={"X-Agent-Key": agent_key})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("commands", [])
    except Exception:
        return []


def _execute_command(cmd: dict[str, Any]) -> None:
    action = cmd.get("action", "")
    target = cmd.get("target", "")
    if action == "restart_service" and target:
        try:
            subprocess.run(["systemctl", "restart", target], timeout=15, check=False)
        except Exception:
            pass
    elif action == "free_memory":
        try:
            subprocess.run(["sync"], timeout=5, check=False)
        except Exception:
            pass


def _load_cfg() -> dict[str, Any]:
    try:
        with open(_CFG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cfg(cfg: dict[str, Any]) -> None:
    with open(_CFG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _register(backend_url: str, onboard_token: str, label: str) -> dict[str, Any]:
    body = json.dumps({"token": onboard_token, "label": label}).encode()
    req  = urllib.request.Request(
        f"{backend_url.rstrip('/')}/agents/register",
        method="POST", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        raise RuntimeError(f"Registration failed ({exc.code}): {raw}") from exc
    except Exception as exc:
        raise RuntimeError(f"Registration failed: {exc}") from exc


def _install_service() -> None:
    script = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    system = platform.system()
    if system == "Windows":
        cmd = (
            f'schtasks /create /tn "{_TASK_NAME}" '
            f'/tr "\\"{script}\\"" '
            f'/sc onlogon /ru "{os.environ.get("USERNAME", "%USERNAME%")}" '
            f'/rl highest /f'
        )
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(result.stderr.strip())
    elif system in ("Linux", "Darwin"):
        unit_dir  = os.path.expanduser("~/.config/systemd/user")
        unit_path = os.path.join(unit_dir, "resilo-agent.service")
        os.makedirs(unit_dir, exist_ok=True)
        with open(unit_path, "w") as f:
            f.write(f"[Unit]\nDescription=Resilo Agent\nAfter=network.target\n\n"
                    f"[Service]\nType=simple\nExecStart={script}\nRestart=always\n\n"
                    f"[Install]\nWantedBy=default.target\n")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", "resilo-agent"], check=False)


def _uninstall_service() -> None:
    system = platform.system()
    if system == "Windows":
        subprocess.run(f'schtasks /delete /tn "{_TASK_NAME}" /f',
                       shell=True, capture_output=True)
    elif system in ("Linux", "Darwin"):
        subprocess.run(["systemctl", "--user", "disable", "--now", "resilo-agent"], check=False)
        unit_path = os.path.expanduser("~/.config/systemd/user/resilo-agent.service")
        if os.path.exists(unit_path):
            os.remove(unit_path)

# ── System tray (optional — bundled by PyInstaller) ───────────────────────────
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ── Design tokens (matches dashboard) ────────────────────────────────────────
BG      = "#0E0D0B"
SURF    = "#161410"
SURF2   = "#1F1D18"
BORDER  = "#2A2820"
AMBER   = "#F59E0B"
TEAL    = "#2DD4BF"
RED     = "#F87171"
TEXT1   = "#F5F0E8"
TEXT2   = "#A89F8C"
TEXT3   = "#6B6357"
TEXT4   = "#4A443D"

DEFAULT_BACKEND = "https://resilo.onrender.com"


# ── Tray icon (drawn programmatically) ───────────────────────────────────────
def _make_tray_icon(color: str = AMBER) -> "Image.Image":
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    r   = int(color.lstrip("#"), 16)
    rgb = ((r >> 16) & 0xFF, (r >> 8) & 0xFF, r & 0xFF)
    d.ellipse([8, 8, 56, 56], fill=rgb)
    return img


# ── App ───────────────────────────────────────────────────────────────────────
class ResilioApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root    = root
        self.cfg     = _load_cfg()
        self._stop   = threading.Event()
        self._thread: threading.Thread | None = None
        self._tray:   Any = None

        self._status  = tk.StringVar(value="OFFLINE")
        self._cpu     = tk.DoubleVar(value=0)
        self._mem     = tk.DoubleVar(value=0)
        self._disk    = tk.DoubleVar(value=0)
        self._label   = tk.StringVar(value="Not connected")
        self._interval = 5.0

        self._build_ui()
        self._apply_saved_config()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        r = self.root
        r.title("Resilo Agent")
        r.configure(bg=BG)
        r.resizable(False, False)
        r.geometry("420x580")

        # ── Title bar area ────────────────────────────────────────────────────
        hdr = tk.Frame(r, bg=SURF, pady=0)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚡  RESILO AGENT", bg=SURF, fg=AMBER,
                 font=("Courier New", 11, "bold"), padx=20, pady=14).pack(side="left")
        tk.Label(hdr, text="v2  ·  AIOps", bg=SURF, fg=TEXT4,
                 font=("Courier New", 9)).pack(side="right", padx=20)
        tk.Frame(r, bg=BORDER, height=1).pack(fill="x")

        # ── Status row ────────────────────────────────────────────────────────
        st_frame = tk.Frame(r, bg=BG, pady=12, padx=20)
        st_frame.pack(fill="x")

        self._dot_canvas = tk.Canvas(st_frame, width=10, height=10, bg=BG,
                                     highlightthickness=0)
        self._dot_canvas.pack(side="left")
        self._dot = self._dot_canvas.create_oval(1, 1, 9, 9, fill=RED, outline="")

        self._status_lbl = tk.Label(st_frame, textvariable=self._status, bg=BG,
                                    fg=RED, font=("Courier New", 10, "bold"))
        self._status_lbl.pack(side="left", padx=(6, 16))

        self._name_lbl = tk.Label(st_frame, textvariable=self._label, bg=BG,
                                  fg=TEXT3, font=("Courier New", 9))
        self._name_lbl.pack(side="left")

        # ── Metrics ───────────────────────────────────────────────────────────
        tk.Frame(r, bg=BORDER, height=1).pack(fill="x", padx=20)
        met_frame = tk.Frame(r, bg=BG, padx=20, pady=14)
        met_frame.pack(fill="x")

        self._bars: dict[str, tk.Canvas] = {}
        self._pct_lbls: dict[str, tk.Label] = {}
        for name, var in [("CPU", self._cpu), ("MEM", self._mem), ("DISK", self._disk)]:
            row = tk.Frame(met_frame, bg=BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=name, bg=BG, fg=TEXT4,
                     font=("Courier New", 9), width=5, anchor="w").pack(side="left")
            c = tk.Canvas(row, width=260, height=6, bg=SURF2,
                          highlightthickness=1, highlightbackground=BORDER)
            c.pack(side="left", padx=(0, 10))
            self._bars[name] = c
            lbl = tk.Label(row, text="—", bg=BG, fg=TEAL,
                           font=("Courier New", 9), width=6, anchor="e")
            lbl.pack(side="left")
            self._pct_lbls[name] = lbl
            # bind variable update
            var.trace_add("write", lambda *_, n=name, v=var: self._update_bar(n, v))

        # ── Config inputs ─────────────────────────────────────────────────────
        tk.Frame(r, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(4, 0))
        cfg_frame = tk.Frame(r, bg=BG, padx=20, pady=14)
        cfg_frame.pack(fill="x")

        for lbl_text, attr, default in [
            ("BACKEND URL", "_backend_var", DEFAULT_BACKEND),
            ("TOKEN",       "_token_var",   ""),
        ]:
            tk.Label(cfg_frame, text=lbl_text, bg=BG, fg=TEXT4,
                     font=("Courier New", 8), anchor="w").pack(fill="x")
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            show = "*" if "TOKEN" in lbl_text else ""
            e = tk.Entry(cfg_frame, textvariable=var, bg=SURF2, fg=TEXT1,
                         insertbackground=AMBER, relief="flat",
                         font=("Courier New", 10), show=show,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=AMBER)
            e.pack(fill="x", pady=(3, 8), ipady=6)
            if "TOKEN" in lbl_text:
                self._token_entry = e

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(r, bg=BG, padx=20)
        btn_frame.pack(fill="x")

        self._conn_btn = self._btn(btn_frame, "CONNECT", self._connect,
                                   AMBER, "#1a1500")
        self._conn_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._svc_btn = self._btn(btn_frame, "INSTALL SERVICE", self._install_svc,
                                  TEXT3, SURF2)
        self._svc_btn.pack(side="left", fill="x", expand=True)

        # ── Log area ──────────────────────────────────────────────────────────
        tk.Frame(r, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(14, 0))
        log_frame = tk.Frame(r, bg=BG, padx=20, pady=10)
        log_frame.pack(fill="both", expand=True)
        tk.Label(log_frame, text="LOG", bg=BG, fg=TEXT4,
                 font=("Courier New", 8)).pack(anchor="w", pady=(0, 4))
        self._log = scrolledtext.ScrolledText(
            log_frame, bg=SURF, fg=TEXT3, font=("Courier New", 9),
            relief="flat", wrap="word", height=8,
            insertbackground=AMBER,
        )
        self._log.pack(fill="both", expand=True)
        self._log.configure(state="disabled")

    def _btn(self, parent: tk.Frame, text: str, cmd, fg: str, bg: str) -> tk.Button:
        b = tk.Button(
            parent, text=text, command=cmd,
            bg=bg, fg=fg, activebackground=AMBER, activeforeground=BG,
            relief="flat", font=("Courier New", 9, "bold"),
            cursor="hand2", pady=8,
        )
        b.bind("<Enter>", lambda _: b.configure(bg=AMBER, fg=BG))
        b.bind("<Leave>", lambda _: b.configure(bg=bg, fg=fg))
        return b

    def _update_bar(self, name: str, var: tk.DoubleVar) -> None:
        pct = var.get()
        c   = self._bars[name]
        c.delete("bar")
        w    = 260
        fill = RED if pct >= 90 else AMBER if pct >= 75 else TEAL
        c.create_rectangle(0, 0, int(w * pct / 100), 6, fill=fill,
                            outline="", tags="bar")
        color = RED if pct >= 90 else AMBER if pct >= 75 else TEAL
        self._pct_lbls[name].configure(text=f"{pct:.0f}%", fg=color)

    # ── Config helpers ────────────────────────────────────────────────────────
    def _apply_saved_config(self) -> None:
        if self.cfg.get("backend_url"):
            self._backend_var.set(self.cfg["backend_url"])
        if self.cfg.get("agent_key"):
            self._log_msg("[info] Saved config found — click CONNECT to resume")
            self._token_var.set("(saved)")
            self._token_entry.configure(show="")

    # ── Logging ───────────────────────────────────────────────────────────────
    def _log_msg(self, msg: str) -> None:
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end", msg + "\n")
            self._log.see("end")
            self._log.configure(state="disabled")
        self.root.after(0, _do)

    # ── Status update (thread-safe) ───────────────────────────────────────────
    def _set_live(self, cpu: float, mem: float, disk: float) -> None:
        def _do():
            self._status.set("LIVE")
            self._status_lbl.configure(fg=TEAL)
            self._dot_canvas.itemconfig(self._dot, fill=TEAL)
            self._cpu.set(cpu)
            self._mem.set(mem)
            self._disk.set(disk)
        self.root.after(0, _do)

    def _set_offline(self) -> None:
        def _do():
            self._status.set("OFFLINE")
            self._status_lbl.configure(fg=RED)
            self._dot_canvas.itemconfig(self._dot, fill=RED)
        self.root.after(0, _do)

    # ── Connect ───────────────────────────────────────────────────────────────
    def _connect(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop.set()
            self._conn_btn.configure(text="CONNECT")
            self._log_msg("[info] Disconnected")
            self._set_offline()
            return

        backend = self._backend_var.get().strip() or DEFAULT_BACKEND
        token   = self._token_var.get().strip()

        if not self.cfg.get("agent_key") and (not token or token == "(saved)"):
            messagebox.showerror("Token required",
                                 "Paste the token from the Resilo dashboard.")
            return

        self._conn_btn.configure(text="DISCONNECT")
        self._log_msg(f"[info] Connecting to {backend} …")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._agent_loop, args=(backend, token), daemon=True
        )
        self._thread.start()

    def _agent_loop(self, backend: str, token: str) -> None:
        cfg = self.cfg

        # ── Registration ──────────────────────────────────────────────────────
        if token and token != "(saved)" and not cfg.get("agent_key"):
            os.environ["RESILO_ONBOARD_TOKEN"] = token
            os.environ["RESILO_BACKEND_URL"]   = backend
            try:
                label  = f"desktop-{socket.gethostname()}"
                result = _register(backend, token, label)
                cfg.update({
                    "backend_url": backend,
                    "org_id":      result["org_id"],
                    "agent_key":   result["agent_key"],
                    "device_id":   result.get("device_id", ""),
                    "label":       label,
                })
                _save_cfg(cfg)
                self.cfg = cfg
                self._log_msg(f"[info] Registered — agent_id={result['agent_id']}")
            except Exception as exc:
                self._log_msg(f"[error] Registration failed: {exc}")
                self.root.after(0, lambda: self._conn_btn.configure(text="CONNECT"))
                self._set_offline()
                return
        elif not cfg.get("agent_key"):
            self._log_msg("[error] No agent key and no token provided")
            self.root.after(0, lambda: self._conn_btn.configure(text="CONNECT"))
            return

        host_info = f"{socket.gethostname()} · {platform.system()} · {os.cpu_count()} cores"
        self.root.after(0, lambda: self._label.set(host_info))

        # ── Heartbeat loop ────────────────────────────────────────────────────
        interval = 5.0
        while not self._stop.is_set():
            try:
                m   = collect(cfg.get("device_id", ""), cfg.get("label", "agent"))
                ok, srv_interval = send(cfg["backend_url"], cfg["org_id"],
                                        cfg["agent_key"], m)
                if ok:
                    interval = srv_interval
                    self._set_live(m["cpu"], m["memory"], m["disk"])
                else:
                    self._log_msg("[warn] Heartbeat failed — retrying…")
                    self._set_offline()

                cmds = _poll_commands(cfg["backend_url"], cfg["agent_key"])
                for cmd in cmds:
                    self._log_msg(f"[cmd] {cmd.get('action')} → {cmd.get('target','')}")
                    _execute_command(cmd)
                if cmds:
                    time.sleep(0.5)
                    continue
            except Exception as exc:
                self._log_msg(f"[error] {exc}")
                self._set_offline()
            time.sleep(interval)

        self._set_offline()

    # ── Install service ───────────────────────────────────────────────────────
    def _install_svc(self) -> None:
        if not self.cfg.get("agent_key"):
            messagebox.showwarning("Not connected",
                                   "Connect first so the agent is registered before installing the service.")
            return
        try:
            _install_service()
            messagebox.showinfo(
                "Service installed",
                "Resilo Agent is now registered as a startup service.\n"
                "It will start automatically on next login and run in the background.",
            )
            self._log_msg("[install] Startup service registered")
        except SystemExit:
            messagebox.showerror("Install failed",
                                 "Could not install service. Try running as Administrator.")

    # ── Close → minimise to tray ──────────────────────────────────────────────
    def _on_close(self) -> None:
        if HAS_TRAY and self._thread and self._thread.is_alive():
            self.root.withdraw()
            self._start_tray()
        else:
            self._stop.set()
            self.root.destroy()

    def _start_tray(self) -> None:
        if not HAS_TRAY:
            return
        connected = self._status.get() == "LIVE"
        icon_img  = _make_tray_icon(TEAL if connected else RED)

        def _show(_icon, _item):
            _icon.stop()
            self._tray = None
            self.root.after(0, self.root.deiconify)

        def _quit(_icon, _item):
            _icon.stop()
            self._stop.set()
            self.root.after(0, self.root.destroy)

        menu  = pystray.Menu(
            pystray.MenuItem("Open Resilo Agent", _show, default=True),
            pystray.MenuItem("Quit", _quit),
        )
        self._tray = pystray.Icon("ResilioAgent", icon_img,
                                  "Resilo Agent — LIVE", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    root = tk.Tk()
    app  = ResilioApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
