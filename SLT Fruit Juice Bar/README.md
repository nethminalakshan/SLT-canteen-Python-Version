# SLT Fruit Juice Bar - Modbus to InfluxDB Collector

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
- **Unit/Slave ID**: `2`
- **Polling Interval**: `5.0` seconds (automatically adjusts for parsing delay)

### InfluxDB Data Schema
- **Measurement**: `SLT Juice_Bar`
- **Tags**:
  - `device`: `SLT Juice`
  - `location`: `Bar`

## Parameters Collected

The following 9 parameters are parsed as Big-Endian Float32 numbers from Modbus input registers (Addresses 1 to 28):

1. `Total_KWh`
2. `Total_Kvarh`
3. `ActivePower`
4. `Reactive_Power`
5. `Apparent_Power`
6. `Voltage_L_N`
7. `Current_`
8. `power_factor1`
9. `Freequency_`

## CLI Display

The script features a colorful, human-readable terminal output:
- **Cycle Cards**: Displays the cycle number, timestamp, and overall system status (**WORKING** in green, **NOT WORKING** in red with details).
- **Tabular View**: Formats metrics in an aligned table (Cyan parameters and Yellow values) for clean visualization.
- **Auto-Compatibility**: Auto-detects and configures Windows consoles for ANSI colors, falling back to clean ASCII layouts to avoid encoding issues.

## Usage

Ensure you have the required dependencies installed:
```bash
pip install pyModbusTCP influxdb-client
```

To run the collector:
```bash
python slt_fruit_juice_bar.py
```
To stop the collector, press `Ctrl + C`.
