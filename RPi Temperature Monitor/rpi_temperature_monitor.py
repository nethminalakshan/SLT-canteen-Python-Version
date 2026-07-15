#!/usr/bin/env python3
"""
RPi Temperature Monitor — SLT Canteen System
=============================================
Reads the Raspberry Pi SoC (CPU) temperature from the Linux thermal zone
interface and writes it to InfluxDB v2 on every polling cycle.

Supported platforms:
  - Raspberry Pi 3 / 4 / 5 (Linux)
  - Any Linux system with /sys/class/thermal/thermal_zone0/temp

Run standalone:
  python3 rpi_temperature_monitor.py

Or let master_launcher.py pick it up automatically (it has the marker below).
"""
# master_launcher: enable

import os
import sys
import re
import time
import math

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ---------------------------------------------------------------------------
# ANSI colour palette (matches the style used by the canteen collector scripts)
# ---------------------------------------------------------------------------
COLOR_RESET  = "\033[0m"
COLOR_BOLD   = "\033[1m"
COLOR_GREEN  = "\033[32m"
COLOR_RED    = "\033[31m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE   = "\033[34m"
COLOR_CYAN   = "\033[36m"
COLOR_MAGENTA= "\033[35m"
COLOR_WHITE  = "\033[37m"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Temperature source — standard Linux thermal zone file.
# All Raspberry Pi models expose the SoC temperature here.
TEMP_SOURCE = "/sys/class/thermal/thermal_zone0/temp"

# Polling interval in seconds
POLL_INTERVAL = 0.3

# Warning / critical thresholds (°C)
TEMP_WARN_C  = 70.0
TEMP_CRIT_C  = 80.0

# InfluxDB measurement name and tags
MEASUREMENT = "RPi_Temperature"
TAG_DEVICE  = "RaspberryPi"
TAG_LOCATION = "SLT_Canteen_Server"

# ---------------------------------------------------------------------------
# Helpers — terminal
# ---------------------------------------------------------------------------

def init_colors() -> None:
    """Enable ANSI virtual-terminal colours on Windows (no-op on Linux)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
        except Exception:
            pass


def visible_len(s: str) -> int:
    """Return printable length of *s*, stripping embedded ANSI codes."""
    return len(re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", s))


def print_divider(char: str = "─", width: int = 72) -> None:
    print(char * width)


def print_banner() -> None:
    """Print a startup banner."""
    width = 72
    print(f"\n{COLOR_BOLD}{COLOR_BLUE}{'═' * width}{COLOR_RESET}")
    title = "  🌡  SLT Canteen — Raspberry Pi Temperature Monitor"
    print(f"{COLOR_BOLD}{COLOR_BLUE}║{COLOR_RESET}{COLOR_BOLD}{title:<{width - 2}}{COLOR_BOLD}{COLOR_BLUE}║{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_BLUE}{'═' * width}{COLOR_RESET}\n")


def _temp_color(temp_c: float) -> str:
    if temp_c >= TEMP_CRIT_C:
        return COLOR_RED + COLOR_BOLD
    if temp_c >= TEMP_WARN_C:
        return COLOR_YELLOW
    return COLOR_GREEN


def print_cycle_header(cycle: int, timestamp: str, status: str,
                       reason: str = "") -> None:
    """
    Print a framed cycle-status card.

    status: "OK" | "WARN" | "CRIT" | "ERROR"
    """
    width = 72
    cycle_str = f" CYCLE #{cycle}  |  {timestamp}"

    if status == "OK":
        status_str  = f" Status: {COLOR_GREEN}{COLOR_BOLD}OK{COLOR_RESET} — Temperature normal"
        status_raw  = " Status: OK — Temperature normal"
    elif status == "WARN":
        status_str  = f" Status: {COLOR_YELLOW}{COLOR_BOLD}WARNING{COLOR_RESET} — High temperature!"
        status_raw  = " Status: WARNING — High temperature!"
    elif status == "CRIT":
        status_str  = (f" Status: {COLOR_RED}{COLOR_BOLD}CRITICAL{COLOR_RESET}"
                       f" — Temperature dangerously high!")
        status_raw  = " Status: CRITICAL — Temperature dangerously high!"
    else:
        status_str  = f" Status: {COLOR_RED}{COLOR_BOLD}ERROR{COLOR_RESET} — {reason}"
        status_raw  = f" Status: ERROR — {reason}"

    border = f"{COLOR_BOLD}{COLOR_BLUE}+{'-' * width}+{COLOR_RESET}"
    def _line(content: str, raw: str) -> str:
        pad = " " * (width - len(raw))
        return f"{COLOR_BOLD}{COLOR_BLUE}|{COLOR_RESET}{content}{pad}{COLOR_BOLD}{COLOR_BLUE}|{COLOR_RESET}"

    print(border)
    print(_line(cycle_str,    cycle_str))
    print(_line(status_str,   status_raw))
    print(border)


def print_temperature_card(temp_c: float, written_ok: bool) -> None:
    """Pretty-print a temperature report card."""
    tc = _temp_color(temp_c)
    db_status = (f"{COLOR_GREEN}✔ Written to InfluxDB{COLOR_RESET}"
                 if written_ok else
                 f"{COLOR_RED}✘ InfluxDB write FAILED{COLOR_RESET}")

    rows = [
        ("Measurement source",  TEMP_SOURCE),
        ("CPU Temperature (°C)", f"{tc}{temp_c:.2f} °C{COLOR_RESET}"),
        ("Warning threshold",   f"{TEMP_WARN_C:.1f} °C"),
        ("Critical threshold",  f"{TEMP_CRIT_C:.1f} °C"),
        ("InfluxDB status",     db_status),
    ]

    # Column widths: label + value
    label_w = max(visible_len(r[0]) for r in rows) + 2
    value_w = max(visible_len(r[1]) for r in rows) + 2

    header_sep = f"+{'-' * (label_w + 2)}+{'-' * (value_w + 2)}+"

    print(header_sep)
    header_label = f"{COLOR_BOLD}{'  Metric':<{label_w}}{COLOR_RESET}"
    header_value = f"{COLOR_BOLD}{'  Value':<{value_w}}{COLOR_RESET}"
    print(f"| {header_label} | {header_value} |")
    print(header_sep)
    for label, value in rows:
        lv = visible_len(label)
        vv = visible_len(value)
        print(f"| {COLOR_CYAN}{label}{COLOR_RESET}{' ' * (label_w - lv)} "
              f"| {value}{' ' * (value_w - vv)} |")
    print(header_sep)


# ---------------------------------------------------------------------------
# Helpers — DB configuration (reuses the same db data.txt as all other scripts)
# ---------------------------------------------------------------------------

def find_db_config() -> str:
    """
    Locate 'db data.txt' searching from the script's directory upward.
    Mirrors the same discovery logic used by all other SLT collector scripts.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir,                   "db data.txt"),
        os.path.join(os.path.dirname(script_dir),  "db data.txt"),
        os.path.join(os.getcwd(),                   "db data.txt"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "Could not locate 'db data.txt' in script, parent, or working directory."
    )


def load_db_config(file_path: str) -> dict:
    """Parse key:value pairs from *file_path* and validate required fields."""
    config: dict = {}
    with open(file_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, val = line.split(":", 1)
            config[key.strip()] = val.strip()

    required = ["token", "org", "IP_ADDRESS", "port", "bucket"]
    missing  = [r for r in required if r not in config]
    if missing:
        raise ValueError(
            f"Missing required fields in {file_path}: {', '.join(missing)}"
        )
    return config


# ---------------------------------------------------------------------------
# Helpers — temperature reading
# ---------------------------------------------------------------------------

def read_cpu_temperature() -> float | None:
    """
    Read the SoC temperature from the Linux thermal zone interface.

    Returns:
        temp_celsius (float)  — on success
        None                  — on failure
    """
    try:
        with open(TEMP_SOURCE, "r") as fh:
            raw = fh.read().strip()
        milli_c = int(raw)          # value is in milli-degrees Celsius
        temp_c  = milli_c / 1000.0

        if math.isnan(temp_c) or math.isinf(temp_c):
            return None

        return round(temp_c, 3)
    except FileNotFoundError:
        # Not running on Linux / not a Raspberry Pi
        return None
    except Exception:
        return None


def classify_temperature(temp_c: float) -> str:
    """Return 'OK', 'WARN', or 'CRIT' based on configured thresholds."""
    if temp_c >= TEMP_CRIT_C:
        return "CRIT"
    if temp_c >= TEMP_WARN_C:
        return "WARN"
    return "OK"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    init_colors()
    print_banner()

    # 1. Load InfluxDB configuration ----------------------------------------
    print(f"{COLOR_BOLD}[INIT]{COLOR_RESET} Loading database configuration …")
    try:
        config_path = find_db_config()
        config      = load_db_config(config_path)
        print(f"{COLOR_GREEN}[INIT]{COLOR_RESET} Config loaded from: {config_path}")
    except Exception as exc:
        print(f"{COLOR_RED}[FATAL]{COLOR_RESET} Database config error: {exc}",
              file=sys.stderr)
        sys.exit(1)

    # 2. Initialise InfluxDB client -------------------------------------------
    influx_url = f"http://{config['IP_ADDRESS']}:{config['port']}"
    token      = config["token"]
    org        = config["org"]
    bucket     = config["bucket"]

    print(f"{COLOR_BOLD}[INIT]{COLOR_RESET} Connecting to InfluxDB at {influx_url}  "
          f"(Org: {org} | Bucket: {bucket})")
    try:
        influx_client = InfluxDBClient(url=influx_url, token=token, org=org)
        write_api     = influx_client.write_api(write_options=SYNCHRONOUS)
        print(f"{COLOR_GREEN}[INIT]{COLOR_RESET} InfluxDB client ready.\n")
    except Exception as exc:
        print(f"{COLOR_RED}[FATAL]{COLOR_RESET} InfluxDB init failed: {exc}",
              file=sys.stderr)
        sys.exit(1)

    # 3. Verify that the temperature file is accessible ----------------------
    print(f"{COLOR_BOLD}[INIT]{COLOR_RESET} Checking temperature source: {TEMP_SOURCE}")
    if not os.path.isfile(TEMP_SOURCE):
        print(
            f"{COLOR_YELLOW}[WARN]{COLOR_RESET} Temperature file not found. "
            f"This script requires a Linux system with a thermal zone interface.\n"
            f"       Expected path: {TEMP_SOURCE}\n"
            f"       Ensure you are running on a Raspberry Pi (or compatible Linux board).",
            file=sys.stderr,
        )
        # Continue anyway so the loop can show useful error messages
    else:
        print(f"{COLOR_GREEN}[INIT]{COLOR_RESET} Temperature source confirmed.\n")

    print(
        f"Starting polling loop — interval: {COLOR_BOLD}{POLL_INTERVAL}s{COLOR_RESET} | "
        f"Warn: {COLOR_YELLOW}{TEMP_WARN_C}°C{COLOR_RESET} | "
        f"Crit: {COLOR_RED}{TEMP_CRIT_C}°C{COLOR_RESET}\n"
        f"Press {COLOR_BOLD}Ctrl+C{COLOR_RESET} to stop.\n"
    )
    print_divider("═")

    cycle    = 0
    try:
        while True:
            loop_start = time.time()
            cycle     += 1
            timestamp  = time.strftime("%Y-%m-%d %H:%M:%S")

            # --- Read temperature -------------------------------------------
            temp_c = read_cpu_temperature()

            if temp_c is None:
                print_cycle_header(cycle, timestamp, "ERROR",
                                   reason=f"Cannot read {TEMP_SOURCE}")
                print(f"{COLOR_RED}  ✘  No temperature data. "
                      f"Is this a Raspberry Pi running Linux?{COLOR_RESET}\n")
            else:
                status  = classify_temperature(temp_c)

                # --- Write to InfluxDB -------------------------------------
                written_ok = False
                try:
                    point = (
                        Point(MEASUREMENT)
                        .tag("device",   TAG_DEVICE)
                        .tag("location", TAG_LOCATION)
                        .field("temperature_c", temp_c)
                        .field("status",        status)   # "OK" / "WARN" / "CRIT"
                    )
                    write_api.write(bucket=bucket, org=org, record=point)
                    written_ok = True
                except Exception as exc:
                    print(f"{COLOR_RED}[DB ERROR]{COLOR_RESET} InfluxDB write failed: {exc}")

                # --- Display -----------------------------------------------
                print_cycle_header(cycle, timestamp, status)
                print()
                print_temperature_card(temp_c, written_ok)

                # Coloured inline summary line (handy when log is scrolled)
                tc = _temp_color(temp_c)
                print(
                    f"\n  {COLOR_BOLD}Summary:{COLOR_RESET}  "
                    f"CPU Temp = {tc}{temp_c:.2f} °C{COLOR_RESET}  |  "
                    f"Status = {tc}{status}{COLOR_RESET}"
                )

            print()  # blank line between cycles

            # --- Maintain polling interval ----------------------------------
            elapsed  = time.time() - loop_start
            sleep_t  = max(0.5, POLL_INTERVAL - elapsed)
            time.sleep(sleep_t)

    except KeyboardInterrupt:
        print(f"\n{COLOR_YELLOW}[STOP]{COLOR_RESET} Keyboard interrupt received. "
              f"Shutting down …")
    finally:
        try:
            influx_client.close()
            print(f"{COLOR_GREEN}[STOP]{COLOR_RESET} InfluxDB connection closed.")
        except Exception:
            pass
        print(f"{COLOR_BOLD}[STOP]{COLOR_RESET} Temperature monitor stopped.")


if __name__ == "__main__":
    main()
