#!/usr/bin/env python3
"""
SLT Fruit Juice Bar Modbus to InfluxDB Collector
Converted from Node-RED Flow
Designed to run on Raspberry Pi
"""

import os
import sys
import time
import struct
import math
import re
from pyModbusTCP.client import ModbusClient
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- ANSI escape codes for styling ---
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_GREEN = "\033[32m"
COLOR_RED = "\033[31m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_CYAN = "\033[36m"

def init_colors():
    """Enables virtual terminal processing on Windows for ANSI colors."""
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def visible_len(s):
    """Calculates visible string length, ignoring ANSI color codes."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return len(ansi_escape.sub('', s))

def print_table(headers, rows):
    """Prints a structured table with box-drawing characters."""
    col_widths = [visible_len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], visible_len(str(val)))
            
    def pad(s, width, col_idx):
        v_len = visible_len(s)
        padding = " " * (width - v_len)
        # Even columns (0, 2, 4...) -> Left-aligned
        # Odd columns (1, 3, 5...) -> Right-aligned
        if col_idx % 2 == 1:
            return padding + s
        else:
            return s + padding

    top = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_line = "|" + "|".join(f" {pad(h, w, i)} " for i, (h, w) in enumerate(zip(headers, col_widths))) + "|"
    divider = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    bottom = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    
    print(top)
    print(header_line)
    print(divider)
    for row in rows:
        row_line = "|" + "|".join(f" {pad(str(val), w, i)} " for i, (val, w) in enumerate(zip(row, col_widths))) + "|"
        print(row_line)
    print(bottom)

def print_cycle_header(cycle_num, timestamp, is_working, error_reason=""):
    """Prints a beautiful status card for the current cycle."""
    width = 70
    title_line = f" CYCLE #{cycle_num} | {timestamp}"
    
    if is_working:
        status_line = f" Status: {COLOR_GREEN}{COLOR_BOLD}WORKING{COLOR_RESET} (All systems OK)"
        status_len = len(" Status: WORKING (All systems OK)")
    else:
        status_line = f" Status: {COLOR_RED}{COLOR_BOLD}NOT WORKING{COLOR_RESET} ({error_reason})"
        status_len = len(f" Status: NOT WORKING ({error_reason})")
        
    border_top    = "+" + "-" * width + "+"
    border_bottom = "+" + "-" * width + "+"
    
    # Pad content lines
    title_padded = title_line + " " * (width - len(title_line))
    status_padded = status_line + " " * (width - status_len)
    
    print(f"{COLOR_BOLD}{COLOR_BLUE}{border_top}{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_BLUE}|{COLOR_RESET}{COLOR_BOLD}{title_padded}{COLOR_RESET}{COLOR_BOLD}{COLOR_BLUE}|{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_BLUE}|{COLOR_RESET}{status_padded}{COLOR_BOLD}{COLOR_BLUE}|{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_BLUE}{border_bottom}{COLOR_RESET}")

def print_metrics_table(data_dict, num_groups=2):
    """Formats metrics dictionary into a multi-column table."""
    items = list(data_dict.items())
    num_items = len(items)
    rows_per_group = math.ceil(num_items / num_groups)
    
    rows = []
    for r in range(rows_per_group):
        row = []
        for g in range(num_groups):
            idx = g * rows_per_group + r
            if idx < num_items:
                k, v = items[idx]
                k_colored = f"{COLOR_CYAN}{k}{COLOR_RESET}"
                if v is None:
                    v_colored = f"{COLOR_RED}None{COLOR_RESET}"
                else:
                    v_colored = f"{COLOR_YELLOW}{v:.3f}{COLOR_RESET}" if isinstance(v, (int, float)) else f"{COLOR_YELLOW}{v}{COLOR_RESET}"
                row.extend([k_colored, v_colored])
            else:
                row.extend(["", ""])
        rows.append(row)
        
    headers = []
    for g in range(num_groups):
        headers.extend([f"{COLOR_BOLD}Parameter{COLOR_RESET}", f"{COLOR_BOLD}Value{COLOR_RESET}"])
        
    print_table(headers, rows)

# --- Configuration Constants ---
MODBUS_HOST = "192.168.1.201"
MODBUS_PORT = 502
MODBUS_UNIT_ID = 2
POLL_INTERVAL = 5.0  # seconds

# --- Helper Functions ---

def find_db_config():
    """
    Search for db data.txt in current, script, and parent directories.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, 'db data.txt'),
        os.path.join(os.path.dirname(script_dir), 'db data.txt'),
        os.path.join(os.getcwd(), 'db data.txt')
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError("Could not locate 'db data.txt' in script, parent, or current working directory.")

def load_db_config(file_path):
    """
    Parses connection parameters from db data.txt.
    """
    config = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or ':' not in line:
                continue
            key, val = line.split(':', 1)
            config[key.strip()] = val.strip()
    
    # Validate required parameters
    required = ['token', 'org', 'IP_ADDRESS', 'port', 'bucket']
    missing = [req for req in required if req not in config]
    if missing:
        raise ValueError(f"Missing required config fields in {file_path}: {', '.join(missing)}")
        
    return config

def read_float32(regs, start_idx):
    """
    Converts two 16-bit registers (4 bytes) to a Float32 value assuming Big-Endian order.
    Equivalent to Buffer.readFloatBE(0) in Node-RED.
    """
    if not regs or len(regs) < start_idx + 2:
        return None
    
    r1 = regs[start_idx]
    r2 = regs[start_idx + 1]
    
    if r1 is None or r2 is None:
        return None
        
    try:
        # Pack two 16-bit unsigned integers (H) as big-endian (>)
        # Unpack as a single big-endian float32 (f)
        packed = struct.pack('>HH', r1, r2)
        val = struct.unpack('>f', packed)[0]
        
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except Exception:
        return None

def ensure_number(value):
    """
    Validates and formats value to 3 decimal places.
    Equivalent to ensureNumber() function in Node-RED flow.
    """
    if value is None or value == "":
        return None
    try:
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        return round(num, 3)
    except (ValueError, TypeError):
        return None

# --- Main Program Loop ---

def main():
    init_colors()
    print("SLT Fruit Juice Bar - Modbus to InfluxDB Collector")
    print("--------------------------------------------------")
    
    # 1. Load Database Configuration
    try:
        config_path = find_db_config()
        config = load_db_config(config_path)
        print(f"Successfully loaded database config from: {config_path}")
    except Exception as e:
        print(f"FATAL: Database configuration error: {e}", file=sys.stderr)
        sys.exit(1)
        
    # 2. Initialize InfluxDB Client
    influx_url = f"http://{config['IP_ADDRESS']}:{config['port']}"
    token = config['token']
    org = config['org']
    bucket = config['bucket']
    
    print(f"Connecting to InfluxDB at: {influx_url} (Org: {org}, Bucket: {bucket})")
    try:
        influx_client = InfluxDBClient(url=influx_url, token=token, org=org)
        write_api = influx_client.write_api(write_options=SYNCHRONOUS)
        print("InfluxDB client initialized.")
    except Exception as e:
        print(f"FATAL: Failed to initialize InfluxDB client: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Initialize Modbus TCP Client
    print(f"Initializing Modbus TCP Client -> {MODBUS_HOST}:{MODBUS_PORT} (Unit/Slave ID: {MODBUS_UNIT_ID})")
    modbus_client = ModbusClient(host=MODBUS_HOST, port=MODBUS_PORT, unit_id=MODBUS_UNIT_ID, auto_open=True)

    print(f"Starting data collection loop (polling every {POLL_INTERVAL} seconds). Press Ctrl+C to exit.\n")
    
    cycle_num = 0
    try:
        while True:
            loop_start = time.time()
            cycle_num += 1
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            is_working = True
            error_reasons = []
            data = {}
            
            # --- Sequence Step 1: Read Block (Address 1, qty 28) ---
            # Node-RED: fc=4 (Read Input Registers)
            regs = modbus_client.read_input_registers(1, 28)
            if not regs:
                is_working = False
                error_reasons.append("Modbus Read Failed")
                regs = []

            # --- Sequence Step 2: Parse & Format Data ---
            if regs:
                # Parse Float32 values according to active Node-RED Parse node
                data = {
                    'Total_KWh':      read_float32(regs, 0),   # Registers 1 & 2
                    'Total_Kvarh':    read_float32(regs, 6),   # Registers 7 & 8
                    'ActivePower':    read_float32(regs, 14),  # Registers 15 & 16
                    'Reactive_Power': read_float32(regs, 16),  # Registers 17 & 18
                    'Apparent_Power': read_float32(regs, 18),  # Registers 19 & 20
                    'Voltage_L_N':    read_float32(regs, 20),  # Registers 21 & 22
                    'Current_':       read_float32(regs, 22),  # Registers 23 & 24
                    'power_factor1':  read_float32(regs, 24),  # Registers 25 & 26
                    'Freequency_':    read_float32(regs, 26)   # Registers 27 & 28
                }

                # --- Sequence Step 3: Write to InfluxDB ---
                # Measurement: SLT Juice_Bar
                # Tags: device="SLT Juice", location="Bar"
                point = Point("SLT Juice_Bar") \
                    .tag("device", "SLT Juice") \
                    .tag("location", "Bar")

                has_fields = False
                written_fields = []
                
                for field_name, val in data.items():
                    processed_val = ensure_number(val)
                    if processed_val is not None:
                        point.field(field_name, processed_val)
                        written_fields.append(field_name)
                        has_fields = True

                if has_fields:
                    try:
                        write_api.write(bucket=bucket, org=org, record=point)
                    except Exception as e:
                        is_working = False
                        error_reasons.append(f"InfluxDB Write Failed: {e}")
                else:
                    is_working = False
                    error_reasons.append("No valid metric data parsed")

            # --- Display Status and Metrics ---
            err_str = ", ".join(error_reasons) if error_reasons else ""
            print_cycle_header(cycle_num, timestamp, is_working, err_str)
            if data:
                print_metrics_table(data, num_groups=1) # 9 parameters fit nicely in 1 group (or 2)
            else:
                print(f"{COLOR_RED}No data parsed in this cycle.{COLOR_RESET}")

            # Calculate sleep duration to offset parsing time and maintain exactly 5-second polling interval
            elapsed = time.time() - loop_start
            sleep_duration = max(0.1, POLL_INTERVAL - elapsed)
            time.sleep(sleep_duration)
            
    except KeyboardInterrupt:
        print("\nStopping collector loop...")
    finally:
        # Clean up clients
        try:
            modbus_client.close()
            print("Modbus connection closed.")
        except Exception:
            pass
        try:
            influx_client.close()
            print("InfluxDB connection closed.")
        except Exception:
            pass
        print("Collector stopped.")

if __name__ == '__main__':
    main()
