# SLT Canteen Monitoring System — Python Version

> **Modbus TCP → InfluxDB** telemetry collector for four SLT canteen / juice bar locations.  
> Converted from the original Node-RED flows to standalone Python scripts with a  
> central auto-restarting supervisor (`master_launcher.py`).

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [System Architecture](#system-architecture)
- [Monitoring Scripts](#monitoring-scripts)
- [Master Launcher](#master-launcher)
- [Configuration](#configuration)
- [Dependencies](#dependencies)
- [How to Run](#how-to-run)
- [Console Output](#console-output)
- [InfluxDB Schema](#influxdb-schema)
- [Troubleshooting](#troubleshooting)

---

## Overview

This project continuously polls power-meter data from **four SLT canteen locations** over **Modbus TCP**, parses the raw 32-bit float registers, and writes structured telemetry points to an **InfluxDB v2** time-series database.

Each collector runs as an independent process. The **master launcher** supervises all four, automatically restarting any script that crashes or exits unexpectedly.

| Location | Script | Modbus Host | Slave ID |
|---|---|---|---|
| Fruit Juice Bar | `slt_fruit_juice_bar.py` | 192.168.1.201 | 2 |
| Rajabojun Canteen | `slt_rajabojun_canteen.py` | 192.168.1.201 | 1 |
| 1st Floor Canteen | `slt_1st_floor_canteen.py` | 192.168.1.200 | 3 |
| 2nd Floor Canteen | `slt_2nd_floor_canteen.py` | 192.168.1.200 | 4 |
| **RPi Board** | `rpi_temperature_monitor.py` | *(Linux thermal zone)* | — |

All scripts share a **single shared config file** (`db data.txt`) in the project root for InfluxDB credentials.

---

## Project Structure

```
SLT canteen Python Version/
|
+-- master_launcher.py                   # Central supervisor — starts & auto-restarts all scripts
+-- db data.txt                          # Shared InfluxDB connection credentials (token, org, IP, bucket)
|
+-- SLT Fruit Juice Bar/
|   +-- slt_fruit_juice_bar.py           # Fruit Juice Bar Modbus collector
|   +-- README.md                        # Script-specific documentation
|
+-- SLT Rajabojun Canteen/
|   +-- slt_rajabojun_canteen.py         # Rajabojun Canteen Modbus collector
|   +-- README.md
|
+-- SLT 1st Floor Canteen/
|   +-- slt_1st_floor_canteen.py         # 1st Floor Canteen Modbus collector
|   +-- README.md
|
+-- SLT 2nd Floor Canteen/
|   +-- slt_2nd_floor_canteen.py         # 2nd Floor Canteen Modbus collector
|   +-- README.md
|
+-- RPi Temperature Monitor/
    +-- rpi_temperature_monitor.py       # Raspberry Pi SoC temperature → InfluxDB monitor
    +-- README.md                        # Script-specific documentation
```

---

## System Architecture

```
                  +------------------------------------+
                  |         master_launcher.py         |
                  |   (Supervisor / Process Manager)   |
                  +------------------+-----------------+
                                     | spawns & supervises
         +---------------------------+----------------------------+
         |                           |                            |
         v                           v                            v                           v
+------------------+  +------------------+  +------------------+  +------------------+
|  Fruit Juice Bar |  | Rajabojun Canteen|  | 1st Floor Canteen|  | 2nd Floor Canteen|
|    Collector     |  |    Collector     |  |    Collector     |  |    Collector     |
+--------+---------+  +--------+---------+  +--------+---------+  +--------+---------+
         |                      |                     |                     |
         |       Modbus TCP port 502                  |                     |
         v                      v                     v                     v
  192.168.1.201          192.168.1.201          192.168.1.200         192.168.1.200
  (Slave ID: 2)          (Slave ID: 1)          (Slave ID: 3)         (Slave ID: 4)
         |                      |                     |                     |
         +----------------------+---------------------+---------------------+
                                            |
                                            v
                                +-----------------------+
                                |     InfluxDB v2       |
                                | Host: 124.43.179.232  |
                                | Port: 8086            |
                                | Org:  SLT             |
                                | Bucket: SLT Canteens  |
                                +-----------------------+
```

---

## Monitoring Scripts

### 1. SLT Fruit Juice Bar

| Property | Value |
|---|---|
| **File** | `SLT Fruit Juice Bar/slt_fruit_juice_bar.py` |
| **Modbus Host** | `192.168.1.201:502` |
| **Slave ID** | `2` |
| **Poll Interval** | 5 seconds |
| **InfluxDB Measurement** | `FruitJuiceBar_Power` |
| **Register Block** | 28 input registers from address 1 (FC4) |
| **Docs** | `SLT Fruit Juice Bar/README.md` |

**Metrics collected:** Total_KWh, Total_Kvarh, Voltage (V1N, V2N, V3N), Current (I1, I2, I3), KW, KVA, KVAR, Power Factor, Frequency.

---

### 2. SLT Rajabojun Canteen

| Property | Value |
|---|---|
| **File** | `SLT Rajabojun Canteen/slt_rajabojun_canteen.py` |
| **Modbus Host** | `192.168.1.201:502` |
| **Slave ID** | `1` |
| **Poll Interval** | 5 seconds |
| **InfluxDB Measurement** | `RajabojunCanteen_Power` |
| **Register Blocks** | Address 1 (Block A) + Address 107 (Block B) |
| **Docs** | `SLT Rajabojun Canteen/README.md` |

**Metrics collected:** Voltage (V1N–V3N, Average), Current (I1–I3, Average), KW, KVA, Power Factor, Frequency, KWh, KVAh, Peak Demand.

---

### 3. SLT 1st Floor Canteen

| Property | Value |
|---|---|
| **File** | `SLT 1st Floor Canteen/slt_1st_floor_canteen.py` |
| **Modbus Host** | `192.168.1.200:502` |
| **Slave ID** | `3` |
| **Poll Interval** | 5 seconds |
| **InfluxDB Measurement** | `FirstFloorCanteen_Power` |
| **Register Blocks** | Address 1 (Block A) + Address 107 (Block B) |
| **Docs** | `SLT 1st Floor Canteen/README.md` |

**Metrics collected:** Full three-phase power metrics — voltage, current, power, energy, power factor, frequency, and peak demand.

---

### 4. SLT 2nd Floor Canteen

| Property | Value |
|---|---|
| **File** | `SLT 2nd Floor Canteen/slt_2nd_floor_canteen.py` |
| **Modbus Host** | `192.168.1.200:502` |
| **Slave ID** | `4` |
| **Poll Interval** | 5 seconds |
| **InfluxDB Measurement** | `SecondFloorCanteen_Power` |
| **Register Blocks** | Address 1 (Block A) + Address 107 (Block B) |
| **Docs** | `SLT 2nd Floor Canteen/README.md` |

**Metrics collected:** Full three-phase power metrics — voltage, current, power, energy, power factor, frequency, and peak demand.

---

### 5. RPi Temperature Monitor

| Property | Value |
|---|---|
| **File** | `RPi Temperature Monitor/rpi_temperature_monitor.py` |
| **Data Source** | `/sys/class/thermal/thermal_zone0/temp` (Linux kernel interface) |
| **Poll Interval** | 10 seconds |
| **InfluxDB Measurement** | `RPi_Temperature` |
| **Dependencies** | `influxdb-client` only (no Modbus library needed) |
| **Docs** | `RPi Temperature Monitor/README.md` |

**Metrics collected:** `temperature_c` (°C), `temperature_f` (°F), `status` (OK / WARN / CRIT).

---

## Master Launcher

**File:** `master_launcher.py`

The master launcher is the **recommended** way to run the full system. It:

- **Auto-bootstraps** a Python virtual environment (`venv/`) on first run — no manual pip installs needed.
- **Installs** all required packages (`pymodbus`, `pyModbusTCP`, `influxdb-client`, `pyserial`, `RPi.GPIO`) automatically.
- **Spawns** all four collector scripts as independent child processes.
- **Monitors** each process and **auto-restarts** it on crash or unexpected exit (15-second restart delay).
- **Opens separate terminal windows** on Windows (CMD) and Linux GUI (lxterminal/xterm) so each script's coloured output is visible independently.
- **Streams output** to the master log on headless Linux / SSH environments.
- **Handles Ctrl+C** cleanly — shuts down all child processes gracefully.

### Dynamic Script Discovery

The launcher scans subdirectories automatically. If a folder has exactly one `.py` file, it is registered automatically. To force-enable a specific script from a multi-file folder, add this comment anywhere in the file:

```python
# master_launcher: enable
```

### Logger Prefix Mapping

| Directory Name | Logger Prefix |
|---|---|
| `SLT Fruit Juice Bar` | `[FruitJuiceBar]` |
| `SLT Rajabojun Canteen` | `[RajabojunCanteen]` |
| `SLT 1st Floor Canteen` | `[FirstFloorCanteen]` |
| `SLT 2nd Floor Canteen` | `[SecondFloorCanteen]` |
| `RPi Temperature Monitor` | `[RPiTemperature]` |

---

## Configuration

### `db data.txt` — Shared InfluxDB Credentials

This file is located in the **project root** and read automatically by all four scripts.

```
token:<your_influxdb_api_token>
org:SLT
IP_ADDRESS:124.43.179.232
port:8086
bucket:SLT Canteens
```

> **Search order:** Each script looks for `db data.txt` in:
> 1. The script's own directory
> 2. **The parent directory (project root)** ← default shared location
> 3. The current working directory

To change the InfluxDB target, edit **only this one file** — all four scripts pick up the change automatically on the next restart.

### Modbus Settings (per-script constants)

Open the relevant `.py` file and edit the constants near the top:

```python
MODBUS_HOST    = "192.168.1.201"   # IP address of the Modbus power meter / gateway
MODBUS_PORT    = 502               # Standard Modbus TCP port
MODBUS_UNIT_ID = 2                 # Slave / Unit ID of the meter
POLL_INTERVAL  = 5.0               # Seconds between each poll cycle
```

---

## Dependencies

| Package | Purpose | Install |
|---|---|---|
| `pyModbusTCP` | Modbus TCP client library | `pip install pyModbusTCP` |
| `pymodbus` | Modbus protocol support | `pip install pymodbus` |
| `influxdb-client` | InfluxDB v2 write API | `pip install influxdb-client` |
| `pyserial` | Serial port support | `pip install pyserial` |
| `RPi.GPIO` / `rpi-lgpio` | GPIO support (Raspberry Pi only) | auto-installed on Linux |

> **Note:** The master launcher installs all dependencies automatically inside a virtual environment on first run. Manual installation is only needed when running scripts directly without the launcher.
>
> ```bash
> pip install pyModbusTCP pymodbus influxdb-client pyserial
> ```

---

## How to Run

### Recommended — Master Launcher (runs all 4 scripts together)

```bash
# Windows
python master_launcher.py

# Linux / Raspberry Pi
python3 master_launcher.py
```

On first run the launcher will:
1. Detect that a virtual environment does not exist and create `venv/`.
2. Install all required packages inside the venv.
3. Re-launch itself inside the venv automatically.
4. Open each collector script in its own terminal window.

### Run a Single Script Manually

```bash
# From project root
python "SLT Fruit Juice Bar/slt_fruit_juice_bar.py"

# Or from inside the script's folder
cd "SLT Fruit Juice Bar"
python slt_fruit_juice_bar.py
```

### Stop Everything

Press **`Ctrl+C`** in the master launcher terminal. All four child processes will be shut down cleanly.

---

## Console Output

Each script produces a structured, ANSI colour-coded display for every polling cycle:

```
+----------------------------------------------------------------------+
| CYCLE #42 | 2026-07-15 09:05:30                                      |
| Status: WORKING (All systems OK)                                     |
+----------------------------------------------------------------------+
+--------------------+---------+--------------------+---------+
| Parameter          |   Value | Parameter          |   Value |
+--------------------+---------+--------------------+---------+
| voltage_v1n        | 230.450 | total_kw           |   7.710 |
| voltage_v2n        | 231.120 | total_kva          |   8.580 |
| voltage_v3n        | 229.880 | average_pf         |   0.900 |
| average_voltage_ln | 230.480 | frequency          |  50.020 |
| current_i1         |  12.340 | total_net_kwh      |12345.67 |
+--------------------+---------+--------------------+---------+
```

**Colour coding:**

| Colour | Meaning |
|---|---|
| Green | `WORKING` status — data read and written successfully |
| Red | `NOT WORKING` status — Modbus read or InfluxDB write failed |
| Cyan | Parameter / field names |
| Yellow | Metric values |

---

## InfluxDB Schema

All measurements are written to the **`SLT Canteens`** bucket under the **`SLT`** organisation.

| Collector | Measurement Name | Fields |
|---|---|---|
| Fruit Juice Bar | `FruitJuiceBar_Power` | Power, energy, voltage, current, PF, frequency |
| Rajabojun Canteen | `RajabojunCanteen_Power` | Power, energy, voltage, current, PF, frequency |
| 1st Floor Canteen | `FirstFloorCanteen_Power` | Power, energy, voltage, current, PF, frequency |
| 2nd Floor Canteen | `SecondFloorCanteen_Power` | Power, energy, voltage, current, PF, frequency |
| **RPi Temperature** | `RPi_Temperature` | `temperature_c`, `temperature_f`, `status` |

Each data point is timestamped at the moment of the successful read.
Numeric values are stored as 64-bit floats, rounded to 3 decimal places.

---

## Troubleshooting

### `FileNotFoundError: Could not locate 'db data.txt'`

The script cannot find the credentials file. Ensure `db data.txt` exists in the **project root** directory with all five required keys: `token`, `org`, `IP_ADDRESS`, `port`, `bucket`.

### Status shows `NOT WORKING — Modbus Read Failed`

The script cannot reach the power meter over the network. Check:
- The Modbus device is powered on and reachable at the configured IP address.
- The correct Slave/Unit ID is set in the script's `MODBUS_UNIT_ID` constant.
- No firewall rule is blocking TCP port `502`.
- Run `ping 192.168.1.201` or `ping 192.168.1.200` to test network reachability.

### InfluxDB write errors

- Confirm the API token in `db data.txt` has **write** permissions for the `SLT Canteens` bucket.
- Verify the InfluxDB server at `124.43.179.232:8086` is accessible from the host machine.
- Run `curl http://124.43.179.232:8086/ping` to test connectivity.

### Colours not showing on Windows CMD

Run via `master_launcher.py` — it enables Windows virtual terminal processing (ANSI) automatically. Alternatively, use **Windows Terminal** or **PowerShell 7+**.

### A script keeps restarting in a loop

The master launcher will restart a script if it exits with an error. Check the individual script's terminal window for the error traceback. Common causes:
- Missing or malformed `db data.txt`.
- Network unreachable at startup.
- Missing Python package — run `pip install pyModbusTCP influxdb-client` manually.

### Running on Raspberry Pi 5

The master launcher detects Raspberry Pi 5 automatically and installs `rpi-lgpio` instead of the incompatible `RPi.GPIO` library. No manual action is needed.

---

*Project maintained by SLT Engineering Team.*