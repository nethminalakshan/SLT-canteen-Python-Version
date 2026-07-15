# RPi Temperature Monitor — SLT Canteen System

> **Raspberry Pi SoC Temperature → InfluxDB** monitor.  
> Reads the CPU temperature from the Linux thermal zone interface, writes every reading to InfluxDB v2, and displays a colour-coded live dashboard in the terminal.

---

## Table of Contents

- [Overview](#overview)
- [What it Measures](#what-it-measures)
- [Console Output](#console-output)
- [Configuration](#configuration)
- [InfluxDB Schema](#influxdb-schema)
- [Thresholds](#thresholds)
- [Dependencies](#dependencies)
- [How to Run](#how-to-run)
- [Troubleshooting](#troubleshooting)

---

## Overview

The script polls `/sys/class/thermal/thermal_zone0/temp` — the standard Linux
kernel interface that exposes the SoC (System-on-Chip) temperature on every
Raspberry Pi model — and pushes the reading to the shared **SLT Canteens**
InfluxDB bucket on every cycle.

It shares the same `db data.txt` credentials file and the same ANSI
colour-coding style as the other SLT canteen collector scripts.

---

## What it Measures

| Field | Unit | Description |
|---|---|---|
| `temperature_c` | °C (float) | SoC CPU temperature in Celsius |
| `status` | string | `"OK"` / `"WARN"` / `"CRIT"` based on thresholds |

All fields are written as a single InfluxDB point on each polling cycle.

---

## Console Output

Every cycle prints a framed status card followed by a detailed metric table:

```
════════════════════════════════════════════════════════════════════════
║  🌡  SLT Canteen — Raspberry Pi Temperature Monitor
════════════════════════════════════════════════════════════════════════

[INIT] Loading database configuration …
[INIT] Config loaded from: /home/pi/SLT canteen Python Version/db data.txt
[INIT] Connecting to InfluxDB at http://124.43.179.232:8086  (Org: SLT | Bucket: SLT Canteens)
[INIT] InfluxDB client ready.

[INIT] Checking temperature source: /sys/class/thermal/thermal_zone0/temp
[INIT] Temperature source confirmed.

Starting polling loop — interval: 10s | Warn: 70.0°C | Crit: 80.0°C
Press Ctrl+C to stop.

+------------------------------------------------------------------------+
| CYCLE #1  |  2026-07-15 09:00:10                                       |
| Status: OK — Temperature normal                                         |
+------------------------------------------------------------------------+

+----------------------------+----------------------------+
| Metric                     | Value                      |
+----------------------------+----------------------------+
| Measurement source         | /sys/class/thermal/...     |
| CPU Temperature (°C)       | 52.31 °C                   |
| Warning threshold          | 70.0 °C                    |
| Critical threshold         | 80.0 °C                    |
| InfluxDB status            | ✔ Written to InfluxDB      |
+----------------------------+----------------------------+

  Summary:  CPU Temp = 52.31 °C  |  Status = OK
```

### Status colour key

| Colour | Status | Meaning |
|---|---|---|
| 🟢 Green | `OK` | Temperature below warning threshold |
| 🟡 Yellow | `WARN` | Temperature at or above `TEMP_WARN_C` (70 °C) |
| 🔴 Red (bold) | `CRIT` | Temperature at or above `TEMP_CRIT_C` (80 °C) |
| 🔴 Red | `ERROR` | Cannot read the temperature file |

---

## Configuration

### Polling and thresholds

Open `rpi_temperature_monitor.py` and edit the constants near the top:

```python
TEMP_SOURCE   = "/sys/class/thermal/thermal_zone0/temp"  # Linux thermal zone file
POLL_INTERVAL = 0.3    # seconds between each reading
TEMP_WARN_C   = 70.0   # warning threshold (°C)
TEMP_CRIT_C   = 80.0   # critical threshold (°C)
```

> **Note:** Raspberry Pi 5 may expose multiple thermal zones
> (`thermal_zone0`, `thermal_zone1` …). The default `thermal_zone0` reports
> the main SoC cluster temperature. Change `TEMP_SOURCE` if you need a
> different zone.

### InfluxDB tags

```python
MEASUREMENT   = "RPi_Temperature"
TAG_DEVICE    = "RaspberryPi"
TAG_LOCATION  = "SLT_Canteen_Server"
```

Edit `TAG_DEVICE` and `TAG_LOCATION` to match the physical placement of your
Raspberry Pi (e.g. `"RPi-1st-Floor"`).

### InfluxDB credentials

Credentials are read automatically from `db data.txt` in the **project root**
— the same shared file used by all other SLT collector scripts.

```
token:<your_influxdb_api_token>
org:SLT
IP_ADDRESS:124.43.179.232
port:8086
bucket:SLT Canteens
```

The script searches for this file in:
1. The script's own directory (`RPi Temperature Monitor/`)
2. **The parent directory (project root)** ← default shared location
3. The current working directory

---

## InfluxDB Schema

```
Measurement : RPi_Temperature
Tags        : device="RaspberryPi", location="SLT_Canteen_Server"
Fields      : temperature_c (float), status (string)
Bucket      : SLT Canteens
Org         : SLT
```

Example Flux query — last 1 hour of CPU temperatures:

```flux
from(bucket: "SLT Canteens")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "RPi_Temperature")
  |> filter(fn: (r) => r._field == "temperature_c")
```

---

## Thresholds

| Threshold | Default | Meaning |
|---|---|---|
| **Warning** (`TEMP_WARN_C`) | `70 °C` | Yellow alert in console; `status = "WARN"` written to DB |
| **Critical** (`TEMP_CRIT_C`) | `80 °C` | Red alert; `status = "CRIT"` written to DB |

Raspberry Pi recommended safe operating range is below **85 °C**.  
Throttling begins at **80 °C** on RPi 4/5. Sustained temperatures above
**85 °C** may cause hardware damage.

---

## Dependencies

| Package | Purpose | Install |
|---|---|---|
| `influxdb-client` | InfluxDB v2 write API | `pip install influxdb-client` |

Only the Python standard library and `influxdb-client` are required.  
No Modbus or GPIO libraries are needed for this script.

> **Tip:** If you run the full system via `master_launcher.py`, all
> dependencies are installed automatically inside the virtual environment.

---

## How to Run

### Standalone

```bash
# From the project root
python3 "RPi Temperature Monitor/rpi_temperature_monitor.py"

# Or from inside the script's folder
cd "RPi Temperature Monitor"
python3 rpi_temperature_monitor.py
```

### Via master launcher

The script contains the marker `# master_launcher: enable` so the
`master_launcher.py` supervisor will discover and manage it automatically
alongside the four canteen collectors:

```bash
python3 master_launcher.py
```

### Stop

Press **`Ctrl+C`** in the terminal running the script (or the master launcher).
The InfluxDB connection is closed cleanly before exit.

---

## Troubleshooting

### `Status: ERROR — Cannot read /sys/class/thermal/thermal_zone0/temp`

- Verify you are running on a **Linux system** (Raspberry Pi or compatible).
- Check file permissions: `ls -l /sys/class/thermal/thermal_zone0/temp`
- On Raspberry Pi 5 with custom kernels, try `thermal_zone1` or `thermal_zone2`.
- On older kernels: `cat /sys/class/thermal/thermal_zone0/temp` should print
  a 5-digit number (e.g. `52310` = 52.31 °C).

### Temperature always shows `None`

- Make sure the script is running on the **Raspberry Pi itself**, not on a
  Windows/macOS development machine.

### InfluxDB write errors

- Confirm the API token in `db data.txt` has **write** permissions on the
  `SLT Canteens` bucket.
- Test connectivity: `curl http://124.43.179.232:8086/ping`

### Colours not showing on Windows

- This script is designed for the **Raspberry Pi terminal**. On Windows,
  run via **Windows Terminal** or **PowerShell 7+** for ANSI colour support.

---

*Part of the SLT Canteen Monitoring System — maintained by the SLT Engineering Team.*
