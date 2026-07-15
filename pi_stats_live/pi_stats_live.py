#!/usr/bin/env python3
"""
Raspberry Pi System Monitor — Color Table Edition (Auto-Install Dependencies)
Terminal-safe symbols (no emoji rendering issues)
"""

import sys
import subprocess
import importlib


# ---------- Auto-install missing dependencies ----------
REQUIRED_PACKAGES = {
    "psutil": "psutil",
    "rich": "rich",
}

def ensure_dependencies():
    missing = []
    for module_name, pip_name in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print(f"[Setup] Missing packages detected: {', '.join(missing)}")
        print("[Setup] Installing now...\n")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "--upgrade", *missing
            ])
        except subprocess.CalledProcessError:
            print("[Setup] Standard install failed — retrying with --break-system-packages "
                  "(common on newer Raspberry Pi OS / Debian 12+)...")
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install",
                    "--break-system-packages", "--upgrade", *missing
                ])
            except subprocess.CalledProcessError:
                print("[Setup] pip install failed. Try manually:")
                print(f"        pip install --break-system-packages {' '.join(missing)}")
                sys.exit(1)
        print("\n[Setup] Dependencies installed successfully. Continuing...\n")


ensure_dependencies()

# ---------- Now safe to import ----------
import psutil
import time
import os
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.columns import Columns
from rich.console import Group
from rich import box

console = Console()

# ---------- Thresholds for color coding ----------
THRESH = {
    "cpu_percent":   {"warn": 70, "crit": 90},
    "cpu_temp":      {"warn": 60, "crit": 75},
    "mem_percent":   {"warn": 75, "crit": 90},
    "disk_percent":  {"warn": 80, "crit": 95},
    "swap_percent":  {"warn": 50, "crit": 80},
    "load1":         {"warn": 2.0, "crit": 4.0},
}


def color_val(value, key, suffix=""):
    if value is None:
        return "[dim]N/A[/dim]"
    t = THRESH.get(key)
    if not t:
        return f"{value}{suffix}"
    if value >= t["crit"]:
        return f"[bold red]{value}{suffix}[/bold red]"
    elif value >= t["warn"]:
        return f"[bold yellow]{value}{suffix}[/bold yellow]"
    return f"[bold green]{value}{suffix}[/bold green]"


def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except FileNotFoundError:
        return None


def run_vcgencmd(args):
    try:
        return subprocess.check_output(["vcgencmd"] + args).decode().strip()
    except Exception:
        return None


def get_gpu_mem():
    out = run_vcgencmd(["get_mem", "gpu"])
    return out.replace("gpu=", "") if out else "N/A"


def get_arm_mem():
    out = run_vcgencmd(["get_mem", "arm"])
    return out.replace("arm=", "") if out else "N/A"


def get_throttle_status():
    out = run_vcgencmd(["get_throttled"])
    if not out:
        return ["N/A"], False
    code = int(out.replace("throttled=", ""), 16)
    flags = {
        0: "Under-voltage NOW", 1: "Freq capped NOW", 2: "Throttled NOW", 3: "Temp limit NOW",
        16: "Under-voltage (past)", 17: "Freq capped (past)",
        18: "Throttled (past)", 19: "Temp limit (past)",
    }
    active = [msg for bit, msg in flags.items() if code & (1 << bit)]
    is_critical = any(code & (1 << b) for b in (0, 1, 2, 3))
    return (active if active else ["OK"]), is_critical


def get_clock_speed():
    out = run_vcgencmd(["measure_clock", "arm"])
    if not out:
        return None
    return round(int(out.split("=")[1]) / 1e6, 1)


def get_voltage(rail="core"):
    out = run_vcgencmd(["measure_volts", rail])
    return out.replace("volt=", "") if out else "N/A"


def get_uptime():
    return round((time.time() - psutil.boot_time()) / 3600, 1)


def collect_stats():
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    load1, load5, load15 = os.getloadavg()
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    throttle_list, throttle_crit = get_throttle_status()

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cpu_percent": cpu_percent,
        "cpu_per_core": cpu_per_core,
        "load1": round(load1, 2), "load5": round(load5, 2), "load15": round(load15, 2),
        "clock_mhz": get_clock_speed(),
        "cpu_temp": get_cpu_temp(),
        "mem_total": round(mem.total / 1e6, 1),
        "mem_used": round(mem.used / 1e6, 1),
        "mem_percent": mem.percent,
        "swap_used": round(swap.used / 1e6, 1),
        "swap_percent": swap.percent,
        "disk_total": round(disk.total / 1e9, 2),
        "disk_used": round(disk.used / 1e9, 2),
        "disk_percent": disk.percent,
        "net_sent": round(net.bytes_sent / 1e6, 1),
        "net_recv": round(net.bytes_recv / 1e6, 1),
        "voltage_core": get_voltage("core"),
        "gpu_mem": get_gpu_mem(),
        "arm_mem": get_arm_mem(),
        "throttle_list": throttle_list,
        "throttle_crit": throttle_crit,
        "uptime_h": get_uptime(),
    }


def status_tag(value, key):
    t = THRESH.get(key)
    if value is None or not t:
        return "-"
    if value >= t["crit"]:
        return "[bold red]!! CRITICAL[/bold red]"
    elif value >= t["warn"]:
        return "[bold yellow]! WARN[/bold yellow]"
    return "[bold green]OK[/bold green]"


def build_display(s):
    # ===== MAIN / CRITICAL TABLE (priority parameters) =====
    main = Table(title="[ MAIN / CRITICAL PARAMETERS ]", box=box.HEAVY_EDGE,
                 title_style="bold white on dark_red", show_lines=True)
    main.add_column("Parameter", style="bold cyan", width=20)
    main.add_column("Value", justify="center")
    main.add_column("Status", justify="center")

    main.add_row("CPU Usage", color_val(s["cpu_percent"], "cpu_percent", "%"),
                 status_tag(s["cpu_percent"], "cpu_percent"))
    main.add_row("CPU Temp", color_val(s["cpu_temp"], "cpu_temp", "°C"),
                 status_tag(s["cpu_temp"], "cpu_temp"))
    main.add_row("RAM Usage", color_val(s["mem_percent"], "mem_percent", "%"),
                 status_tag(s["mem_percent"], "mem_percent"))
    main.add_row("Disk Usage", color_val(s["disk_percent"], "disk_percent", "%"),
                 status_tag(s["disk_percent"], "disk_percent"))
    main.add_row("Load Avg (1m)", color_val(s["load1"], "load1"),
                 status_tag(s["load1"], "load1"))

    throttle_color = "bold red" if s["throttle_crit"] else "bold green"
    throttle_flag = "[bold red]!![/bold red]" if s["throttle_crit"] else "[bold green]OK[/bold green]"
    main.add_row("Power/Throttle",
                 f"[{throttle_color}]{', '.join(s['throttle_list'])}[/{throttle_color}]",
                 throttle_flag)

    # ===== CPU DETAIL TABLE =====
    cpu_t = Table(title="[ CPU DETAILS ]", box=box.SIMPLE_HEAVY)
    cpu_t.add_column("Core", style="cyan")
    cpu_t.add_column("Usage %")
    for i, pct in enumerate(s["cpu_per_core"]):
        cpu_t.add_row(f"Core {i}", color_val(pct, "cpu_percent", "%"))
    cpu_t.add_row("Clock Speed", f"{s['clock_mhz']} MHz")
    cpu_t.add_row("Load 5m / 15m", f"{s['load5']} / {s['load15']}")

    # ===== MEMORY / DISK TABLE =====
    mem_t = Table(title="[ MEMORY & STORAGE ]", box=box.SIMPLE_HEAVY)
    mem_t.add_column("Item", style="magenta")
    mem_t.add_column("Value")
    mem_t.add_row("RAM Used", f"{s['mem_used']} / {s['mem_total']} MB")
    mem_t.add_row("Swap Used", f"{s['swap_used']} MB ({color_val(s['swap_percent'],'swap_percent','%')})")
    mem_t.add_row("Disk Used", f"{s['disk_used']} / {s['disk_total']} GB")
    mem_t.add_row("GPU Mem Split", s["gpu_mem"])
    mem_t.add_row("ARM Mem Split", s["arm_mem"])

    # ===== POWER / NETWORK TABLE =====
    misc_t = Table(title="[ POWER & NETWORK ]", box=box.SIMPLE_HEAVY)
    misc_t.add_column("Item", style="yellow")
    misc_t.add_column("Value")
    misc_t.add_row("Core Voltage", f"{s['voltage_core']} V")
    misc_t.add_row("Network Sent", f"{s['net_sent']} MB")
    misc_t.add_row("Network Recv", f"{s['net_recv']} MB")
    misc_t.add_row("Uptime", f"{s['uptime_h']} hrs")

    header = Panel(f"[bold white]Raspberry Pi Live Monitor[/bold white]  |  {s['timestamp']}",
                   style="on grey23")

    bottom_row = Columns([cpu_t, mem_t, misc_t], equal=True, expand=True)
    return Group(header, main, bottom_row)


if __name__ == "__main__":
    try:
        with Live(console=console, refresh_per_second=1, screen=True) as live:
            while True:
                stats = collect_stats()
                live.update(build_display(stats))
                time.sleep(4)
    except KeyboardInterrupt:
        console.print("\n[bold red]Stopped by user.[/bold red]")
