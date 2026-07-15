# SLT Rajabojun Canteen - Modbus to InfluxDB Collector

A self-contained Python-based collector designed to poll energy metrics from a Modbus device and write them to an InfluxDB database. Designed to run continuously as a background service on a Raspberry Pi or local system.

## Configuration

The script reads its database connection parameters from a shared file named `db data.txt` located in either the script directory, its parent directory, or the current working directory.

### InfluxDB Settings (from `db data.txt`)
- **Host IP & Port**: Loaded from `IP_ADDRESS` and `port` fields.
- **Organization & Bucket**: Loaded from `org` and `bucket` fields.
- **Authentication Token**: Loaded from the `token` field.

### Modbus Telemetry Settings
- **Modbus Host IP**: `192.168.1.201`
- **Modbus Port**: `502`
- **Unit/Slave ID**: `1`
- **Polling Interval**: `5.0` seconds (automatically adjusts for parsing and sequence delays)

### InfluxDB Data Schema
- **Measurement**: `Rajabojun_canteen`
- **Tags**:
  - `device`: `Rajabojun`
  - `location`: `Canteen`

## Parameters Collected

The following 25 parameters are parsed as Big-Endian Float32 numbers from Modbus input registers across two distinct sequence blocks:

### Block A (Address 1, Qty 62)
1. `voltage_v1n`
2. `voltage_v2n`
3. `voltage_v3n`
4. `average_voltage_ln`
5. `current_i1`
6. `current_i2`
7. `current_i3`
8. `average_current` (calculated programmatically)
9. `kw1`
10. `kw2`
11. `kw3`
12. `kva1`
13. `kva2`
14. `kva3`
15. `total_kw`
16. `total_kva`
17. `pf1`
18. `pf2`
19. `pf3`
20. `average_pf`
21. `frequency`
22. `total_net_kwh`
23. `total_net_kvah`

### Block B (Address 693, Qty 8) - Polled after a 500ms delay
24. `max_i1_demand`
25. `max_i2_demand`
26. `max_i3_demand`
27. `max_avg_i_demand`

## CLI Display

The script features a colorful, human-readable terminal output:
- **Cycle Cards**: Displays the cycle number, timestamp, and overall system status (**WORKING** in green, **NOT WORKING** in red with details).
- **Tabular View**: Formats the 25 metrics side-by-side in a compact 4-column table (Cyan parameters and Yellow values) to optimize vertical screen space.
- **Auto-Compatibility**: Auto-detects and configures Windows consoles for ANSI colors, falling back to clean ASCII layouts to avoid encoding issues.

## Usage

Ensure you have the required dependencies installed:
```bash
pip install pyModbusTCP influxdb-client
```

To run the collector:
```bash
python slt_rajabojun_canteen.py
```
To stop the collector, press `Ctrl + C`.
