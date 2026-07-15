"""
=============================================================================
  SLT Canteens Master Launcher
=============================================================================
  Project     : SLT Canteen Python Version
  Description : Starts all four Canteen monitoring scripts simultaneously as
                independent background processes and keeps them running.
                If any script crashes or exits unexpectedly, it is
                automatically restarted after a configurable delay.

                AUTOMATIC BOOTSTRAPPING:
                When run, this script automatically detects if it is running
                in a virtual environment. If not, it creates a virtual env ("venv"),
                installs all required dependencies (pyModbusTCP, pymodbus, 
                influxdb-client, and RPi.GPIO on Linux), and re-executes itself
                inside the virtual environment.

  Scripts launched:
    1. slt_fruit_juice_bar.py      - Fruit Juice Bar Modbus  -> InfluxDB
    2. slt_rajabojun_canteen.py    - Rajabojun Canteen Modbus -> InfluxDB
    3. slt_1st_floor_canteen.py    - 1st Floor Canteen Modbus -> InfluxDB
    4. slt_2nd_floor_canteen.py    - 2nd Floor Canteen Modbus -> InfluxDB

  HOW TO RUN:
    python3 master_launcher.py

  STOP:
    Press Ctrl+C  (all child scripts are shut down cleanly)

=============================================================================
"""

import subprocess
import threading
import time
import sys
import os
import signal
import logging
import re
from pathlib import Path
from datetime import datetime

# =============================================================================
#  CONFIGURATION & DYNAMIC DISCOVERY
# =============================================================================

# Base directory = folder where this master_launcher.py lives
BASE_DIR = Path(__file__).resolve().parent

# Hardcoded pretty names mapping for the initial scripts to maintain log compatibility
PRETTY_NAMES = {
    "SLT Fruit Juice Bar": "FruitJuiceBar",
    "SLT Rajabojun Canteen": "RajabojunCanteen",
    "SLT 1st Floor Canteen": "FirstFloorCanteen",
    "SLT 2nd Floor Canteen": "SecondFloorCanteen",
}

def discover_scripts() -> list:
    """
    Dynamically scans direct subdirectories of BASE_DIR to find python monitoring scripts.
    - If a directory contains exactly one .py file, it registers it.
    - If it contains multiple, it checks for a marker comment ("master_launcher: enable")
      or a script name matching the directory name.
    - Falls back to the hardcoded four original scripts if discovery is empty or fails.
    """
    discovered = []
    exclude_dirs = {".git", "venv", "__pycache__", ".github", ".agents", "db_details"}
    
    # Hardcoded fallback list in case discovery finds nothing or raises an exception
    fallback_scripts = [
        {
            "name":          "FruitJuiceBar",
            "path":          BASE_DIR / "SLT Fruit Juice Bar" / "slt_fruit_juice_bar.py",
            "restart_delay": 15,
        },
        {
            "name":          "RajabojunCanteen",
            "path":          BASE_DIR / "SLT Rajabojun Canteen"  / "slt_rajabojun_canteen.py",
            "restart_delay": 15,
        },
        {
            "name":          "FirstFloorCanteen",
            "path":          BASE_DIR / "SLT 1st Floor Canteen"        / "slt_1st_floor_canteen.py",
            "restart_delay": 15,
        },
        {
            "name":          "SecondFloorCanteen",
            "path":          BASE_DIR / "SLT 2nd Floor Canteen"     / "slt_2nd_floor_canteen.py",
            "restart_delay": 15,
        },
    ]

    try:
        for item in BASE_DIR.iterdir():
            if item.is_dir() and item.name not in exclude_dirs and not item.name.startswith("."):
                py_files = list(item.glob("*.py"))
                if not py_files:
                    continue
                
                target_file = None
                if len(py_files) == 1:
                    target_file = py_files[0]
                else:
                    # Look for explicit marker in code comments
                    for py_file in py_files:
                        try:
                            with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                                content = "".join([f.readline() for _ in range(30)])
                                if "master_launcher: enable" in content or "launcher: enable" in content:
                                    target_file = py_file
                                    break
                        except Exception:
                            pass
                    
                    # Match filename with directory name (normalized)
                    if not target_file:
                        norm_dir = item.name.lower().replace(" ", "_").replace("-", "_")
                        for py_file in py_files:
                            norm_file = py_file.stem.lower().replace(" ", "_").replace("-", "_")
                            if norm_file == norm_dir or norm_file in norm_dir or norm_dir in norm_file:
                                target_file = py_file
                                break

                    # Fallback to the first non-special Python file
                    if not target_file:
                        for py_file in py_files:
                            if py_file.name not in ("__init__.py", "setup.py"):
                                target_file = py_file
                                break

                if target_file:
                    raw_name = item.name
                    if raw_name in PRETTY_NAMES:
                        name_clean = PRETTY_NAMES[raw_name]
                    else:
                        # Generate a clean CamelCase name
                        name_clean = re.sub(r'^\d+\s*', '', raw_name)
                        name_clean = "".join(word.capitalize() for word in re.split(r'[\s_\-]+', name_clean) if word)
                    
                    discovered.append({
                        "name": name_clean,
                        "path": target_file.resolve(),
                        "restart_delay": 15
                    })
    except Exception:
        pass

    if not discovered:
        return fallback_scripts
    
    discovered.sort(key=lambda s: s["name"])
    return discovered

# All scripts dynamically loaded
SCRIPTS = discover_scripts()

# Python interpreter to use for all child scripts
# Will be set to the virtual environment's python once bootstrapped
PYTHON_EXE = sys.executable

# Maximum restart attempts per script (0 = unlimited restarts)
MAX_RESTARTS = 0

# Logging for the master launcher itself
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# ANSI Escape Codes for Colors
COLOR_RESET   = "\033[0m"
COLOR_GREEN   = "\033[92m"  # OK / Success
COLOR_RED     = "\033[91m"  # Fail / Error
COLOR_YELLOW  = "\033[93m"  # Warn / Wait
COLOR_BLUE    = "\033[94m"  # Info
COLOR_CYAN    = "\033[96m"  # Run / Stop / Start
COLOR_MAGENTA = "\033[95m"  # Process Prefixes

def init_ansi() -> None:
    """Enable ANSI virtual terminal processing on Windows if applicable."""
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hStdout = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(hStdout, ctypes.byref(mode)):
                kernel32.SetConsoleMode(hStdout, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass

class ColoredFormatter(logging.Formatter):
    """Custom logging formatter that adds ANSI colors to log levels, status brackets, and process names."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Get formatted base message
        message = super().format(record)
        
        # Color mapping for bracket tags
        replacements = {
            "[ OK ]": f"{COLOR_GREEN}[ OK ]{COLOR_RESET}",
            "[OK  ]": f"{COLOR_GREEN}[OK  ]{COLOR_RESET}",
            "[FAIL]": f"{COLOR_RED}[FAIL]{COLOR_RESET}",
            "[ERR ]": f"{COLOR_RED}[ERR ]{COLOR_RESET}",
            "[WARN]": f"{COLOR_YELLOW}[WARN]{COLOR_RESET}",
            "[WAIT]": f"{COLOR_YELLOW}[WAIT]{COLOR_RESET}",
            "[INFO]": f"{COLOR_BLUE}[INFO]{COLOR_RESET}",
            "[RUN ]": f"{COLOR_CYAN}[RUN ]{COLOR_RESET}",
            "[STOP]": f"{COLOR_CYAN}[STOP]{COLOR_RESET}",
            "[EXIT]": f"{COLOR_CYAN}[EXIT]{COLOR_RESET}",
        }
        
        for tag, color_tag in replacements.items():
            if tag in message:
                message = message.replace(tag, color_tag)
                
        # Color the log levels in brackets
        message = message.replace("[INFO    ]", f"{COLOR_BLUE}[INFO    ]{COLOR_RESET}")
        message = message.replace("[WARNING ]", f"{COLOR_YELLOW}[WARNING ]{COLOR_RESET}")
        message = message.replace("[ERROR   ]", f"{COLOR_RED}[ERROR   ]{COLOR_RESET}")
        
        # Color alphanumeric process prefixes (e.g., [MASTER], [PowerAnalyzers], etc.)
        # Matches any prefix like [Name] where length is 3-25 chars and has no spaces
        message = re.sub(r'(\[[a-zA-Z0-9_]{3,25}\])', f"{COLOR_MAGENTA}\\1{COLOR_RESET}", message)
        
        return message

# =============================================================================
#  END OF CONFIGURATION
# =============================================================================


# =============================================================================
#  GLOBAL SHUTDOWN FLAG
# =============================================================================

# Set to True when the user presses Ctrl+C or SIGTERM is received.
# Supervisor threads check this flag and stop restarting their script.
_shutdown_event = threading.Event()


# =============================================================================
#  LOGGING SETUP
# =============================================================================

def setup_logging() -> logging.Logger:
    """Configure logging for the master launcher process."""
    init_ansi()
    
    handler = logging.StreamHandler(sys.stdout)
    formatter = ColoredFormatter(
        fmt="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt=LOG_DATEFMT
    )
    handler.setFormatter(formatter)
    
    root_log = logging.getLogger()
    root_log.setLevel(logging.INFO)
    for h in list(root_log.handlers):
        root_log.removeHandler(h)
    root_log.addHandler(handler)
    
    return logging.getLogger("Master")


# =============================================================================
#  AUTOMATIC ENVIRONMENT BOOTSTRAPPER (PEP 668 bypass & setup)
# =============================================================================

def check_and_bootstrap() -> None:
    """
    Checks if the script is running inside the virtual environment ('venv').
    If not:
      1. Creates 'venv' if it doesn't exist.
      2. Installs dependencies (pymodbus, influxdb-client, and RPi.GPIO on Linux).
      3. Re-executes the current script inside the virtual environment.
    """
    venv_dir = BASE_DIR / "venv"
    
    if os.name == 'nt':
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    # Convert to absolute strings for matching
    venv_python_str = str(venv_python.resolve())
    current_python_str = str(Path(sys.executable).resolve())

    if current_python_str != venv_python_str:
        print("[BOOTSTRAP] Checking virtual environment...")

        # 1. Create virtual environment if it doesn't exist
        if not venv_python.exists():
            print(f"[BOOTSTRAP] Creating virtual environment in: {venv_dir}")
            try:
                import venv
                venv.create(str(venv_dir), with_pip=True, system_site_packages=True)
                print("[BOOTSTRAP] Virtual environment created successfully.")
            except Exception as exc:
                print(f"[BOOTSTRAP] [ERROR] Failed to create virtual environment: {exc}")
                print("[BOOTSTRAP] Please ensure python3-venv / python3-full is installed on your OS.")
                sys.exit(1)
        else:
            # If venv exists, ensure system-site-packages is enabled so we can use system GPIO drivers
            pyvenv_cfg = venv_dir / "pyvenv.cfg"
            if pyvenv_cfg.exists():
                try:
                    cfg_content = pyvenv_cfg.read_text(encoding="utf-8")
                    if "include-system-site-packages = false" in cfg_content:
                        print("[BOOTSTRAP] Enabling system site packages in virtual environment...")
                        cfg_content = cfg_content.replace(
                            "include-system-site-packages = false",
                            "include-system-site-packages = true"
                        )
                        pyvenv_cfg.write_text(cfg_content, encoding="utf-8")
                except Exception:
                    pass

        # 2. Install/Upgrade required libraries inside the virtual environment
        print("[BOOTSTRAP] Ensuring dependencies are installed in virtual environment...")
        deps = ["pymodbus", "pyModbusTCP", "influxdb-client", "pyserial"]
        if os.name != 'nt':
            # Check if we are on a Raspberry Pi 5 to use the rpi-lgpio compatibility library
            is_pi5 = False
            try:
                if os.path.exists("/proc/device-tree/model"):
                    with open("/proc/device-tree/model", "r") as f:
                        if "raspberry pi 5" in f.read().lower():
                            is_pi5 = True
            except Exception:
                pass

            if is_pi5:
                print("[BOOTSTRAP] Raspberry Pi 5 detected. Ensuring rpi-lgpio is used (removing RPi.GPIO).")
                try:
                    subprocess.call([venv_python_str, "-m", "pip", "uninstall", "-y", "RPi.GPIO"])
                except Exception:
                    pass
                deps.append("rpi-lgpio")
            else:
                deps.append("RPi.GPIO")

        try:
            # Upgrade pip inside the virtual environment first
            subprocess.check_call([venv_python_str, "-m", "pip", "install", "--upgrade", "pip"])
            # Install project dependencies
            subprocess.check_call([venv_python_str, "-m", "pip", "install"] + deps)
            
            # Check for any requirements.txt files in the workspace (ignoring the venv directory itself)
            for req_file in BASE_DIR.glob("**/requirements.txt"):
                if "venv" not in req_file.parts:
                    print(f"[BOOTSTRAP] Found requirements file: {req_file.relative_to(BASE_DIR)}")
                    print(f"[BOOTSTRAP] Installing dependencies from: {req_file.name}")
                    subprocess.check_call([venv_python_str, "-m", "pip", "install", "-r", str(req_file)])

            print("[BOOTSTRAP] Dependencies verified/installed successfully.")
        except subprocess.CalledProcessError as exc:
            print(f"[BOOTSTRAP] [ERROR] Failed to install dependencies: {exc}")
            if os.name != 'nt':
                print("\n[TIP] If installing GPIO / lgpio libraries failed, please run the following commands on your system:")
                print("      sudo apt update")
                print("      sudo apt install python3-rpi-lgpio -y")
                print("      Or install swig for building packages from source: sudo apt install swig -y\n")
            sys.exit(1)

        # 3. Re-execute the master script inside the virtual environment
        print("[BOOTSTRAP] Launching Master Supervisor in the virtual environment...")
        try:
            if os.name == 'nt':
                # Windows process spawning
                ret = subprocess.call([venv_python_str] + sys.argv)
                sys.exit(ret)
            else:
                # Unix/Linux process replacement (clean execv)
                os.execv(venv_python_str, [venv_python_str] + sys.argv)
        except Exception as exc:
            print(f"[BOOTSTRAP] [ERROR] Failed to re-execute process: {exc}")
            sys.exit(1)


# =============================================================================
#  OUTPUT READER
# =============================================================================

def _stream_reader(stream, prefix: str, log_fn) -> None:
    """
    Read lines from a subprocess stream (stdout or stderr) and forward
    each line to the master logger with the script name as a prefix.
    """
    try:
        for line in iter(stream.readline, ""):
            stripped = line.rstrip()
            if stripped:
                log_fn("%s %s", prefix, stripped)
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


# =============================================================================
#  SCRIPT SUPERVISOR
# =============================================================================

def run_script_supervisor(script: dict, log: logging.Logger) -> None:
    """
    Supervisor function for ONE script. Runs in its own thread.
    """
    name          = script["name"]
    path          = script["path"]
    restart_delay = script["restart_delay"]
    prefix        = f"[{name}]"
    restarts      = 0

    if not path.exists():
        log.error("%s [FAIL] Script not found: %s  --  Supervisor will NOT start.", prefix, path)
        return

    log.info("%s [INFO] Script found: %s", prefix, path)

    while not _shutdown_event.is_set():
        start_time = time.monotonic()
        log.info(
            "%s [RUN ] Starting (restart #%d)  python=%s",
            prefix, restarts, PYTHON_EXE,
        )

        try:
            # We run with "-u" (unbuffered) so logs stream in real-time
            proc = None
            stdout_stream = None
            stderr_stream = None
            
            # Check operating system to spawn in a new console/terminal window if available
            if os.name == 'nt':
                # Windows: Spawn in a new CMD window using CREATE_NEW_CONSOLE (0x00000010)
                proc = subprocess.Popen(
                    [PYTHON_EXE, "-u", str(path)],
                    cwd          = str(path.parent),
                    creationflags=0x00000010
                )
            elif os.name != 'nt' and "DISPLAY" in os.environ:
                # Linux with Desktop GUI: Try to spawn in a separate terminal window.
                # Crucial: For lxterminal, we must pass the '--no-remote' flag. Without it,
                # lxterminal daemonizes and exits with 0 immediately, causing the supervisor
                # to think the process exited and loop infinitely opening new windows.
                success = False
                for term in [
                    ["lxterminal", "--no-remote", "-t", name, "-e"],
                    ["x-terminal-emulator", "-t", name, "-e"],
                    ["xterm", "-title", name, "-e"]
                ]:
                    try:
                        # Wrap execution in bash to keep terminal open on unexpected exits so users can read errors
                        cmd_str = f"bash -c '{PYTHON_EXE} -u \"{path}\"; echo; read -p \"Process exited. Press Enter to close window...\"'"
                        proc = subprocess.Popen(
                            term + [cmd_str],
                            cwd          = str(path.parent),
                            start_new_session = True
                        )
                        success = True
                        break
                    except Exception:
                        pass
                
                if not success:
                    # Fallback to background piped streams if terminal emulator fails
                    proc = subprocess.Popen(
                        [PYTHON_EXE, "-u", str(path)],
                        stdout       = subprocess.PIPE,
                        stderr       = subprocess.PIPE,
                        cwd          = str(path.parent),
                        bufsize      = 1,
                        text         = True,
                        encoding     = "utf-8",
                        errors       = "replace",
                        start_new_session = True
                    )
                    stdout_stream = proc.stdout
                    stderr_stream = proc.stderr
            else:
                # Linux Headless / SSH: Spawn as background supervisor with piped streams
                proc = subprocess.Popen(
                    [PYTHON_EXE, "-u", str(path)],
                    stdout       = subprocess.PIPE,
                    stderr       = subprocess.PIPE,
                    cwd          = str(path.parent),
                    bufsize      = 1,
                    text         = True,
                    encoding     = "utf-8",
                    errors       = "replace",
                    start_new_session = True
                )
                stdout_stream = proc.stdout
                stderr_stream = proc.stderr

            log.info("%s [OK  ] Process started   PID=%d", prefix, proc.pid)

            if stdout_stream is not None and proc.stdout is not None:
                t_out = threading.Thread(
                    target  = _stream_reader,
                    args    = (proc.stdout, prefix, log.info),
                    daemon  = True,
                    name    = f"{name}-stdout",
                )
                t_out.start()
            if stderr_stream is not None and proc.stderr is not None:
                t_err = threading.Thread(
                    target  = _stream_reader,
                    args    = (proc.stderr, prefix, log.warning),
                    daemon  = True,
                    name    = f"{name}-stderr",
                )
                t_err.start()

            # Wait for process to exit or monitor shutdown
            while True:
                try:
                    proc.wait(timeout=1.0)
                    break
                except subprocess.TimeoutExpired:
                    if _shutdown_event.is_set():
                        log.info("%s [STOP] Shutdown requested - terminating PID=%d ...", prefix, proc.pid)
                        if os.name != 'nt':
                            try:
                                # Terminate entire process group (terminal + shell + python)
                                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                            except Exception:
                                proc.terminate()
                        else:
                            proc.terminate()
                            
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            if os.name != 'nt':
                                try:
                                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                                except Exception:
                                    proc.kill()
                            else:
                                proc.kill()
                        break

            exit_code = proc.returncode
            run_secs  = time.monotonic() - start_time

            if _shutdown_event.is_set():
                log.info(
                    "%s [STOP] Process stopped for shutdown  PID=%d  exit=%s  ran=%.1fs",
                    prefix, proc.pid, exit_code, run_secs,
                )
                return

            log.warning(
                "%s [WARN] Process EXITED unexpectedly  PID=%d  exit=%s  ran=%.1fs",
                prefix, proc.pid, exit_code, run_secs,
            )
            restarts += 1

            if MAX_RESTARTS > 0 and restarts > MAX_RESTARTS:
                log.error("%s [FAIL] Max restarts reached - stopping.", prefix)
                return

            log.info(
                "%s [WAIT] Restarting in %d seconds ... (restart #%d)",
                prefix, restart_delay, restarts,
            )
            _shutdown_event.wait(timeout=restart_delay)

        except FileNotFoundError:
            log.error("%s [FAIL] Could not start: Python not found at '%s'", prefix, PYTHON_EXE)
            _shutdown_event.wait(timeout=restart_delay)
        except Exception as exc:
            log.exception("%s [ERR ] Unexpected supervisor error: %s", prefix, exc)
            _shutdown_event.wait(timeout=restart_delay)


# =============================================================================
#  MAIN ENTRY
# =============================================================================

def main() -> None:
    # First: Ensure environment is bootstrapped/ready in venv
    check_and_bootstrap()

    # Second: Initialize logging inside the venv process
    log = setup_logging()

    global PYTHON_EXE
    PYTHON_EXE = sys.executable

    log.info("============================================================")
    log.info("   OTS Master Launcher (Supervisor)")
    log.info("============================================================")
    log.info("   Base directory : %s", BASE_DIR)
    log.info("   Python (Venv)  : %s", PYTHON_EXE)
    log.info("   Scripts        : %d", len(SCRIPTS))
    for s in SCRIPTS:
        exists_text = "[ OK ]" if s["path"].exists() else "[FAIL]"
        log.info("    %s %s  ->  %s", exists_text, s["name"], s["path"].name)
    log.info("   Press Ctrl+C to stop all scripts.")
    log.info("============================================================")

    found = [s for s in SCRIPTS if s["path"].exists()]
    if not found:
        log.error("[FAIL] No script files found under %s -- Exiting.", BASE_DIR)
        sys.exit(1)

    def _sigterm_handler(signum, frame):
        log.info("[STOP] SIGTERM received - shutting down all scripts ...")
        _shutdown_event.set()

    signal.signal(signal.SIGTERM, _sigterm_handler)

    threads = []
    for script in SCRIPTS:
        t = threading.Thread(
            target = run_script_supervisor,
            args   = (script, log),
            name   = f"supervisor-{script['name']}",
            daemon = False,
        )
        t.start()
        threads.append(t)
        log.info("[RUN ] [MASTER] Supervisor started for '%s'", script["name"])

    log.info("[INFO] [MASTER] All supervisors running. Waiting for Ctrl+C ...")
    try:
        while not _shutdown_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("[STOP] [MASTER] Ctrl+C received - shutting down all scripts ...")
        _shutdown_event.set()

    log.info("[WAIT] [MASTER] Waiting for all child processes to stop ...")
    for t in threads:
        t.join(timeout=15)

    log.info("[EXIT] [MASTER] All scripts stopped. Master launcher exited cleanly.")


# =============================================================================
if __name__ == "__main__":
    main()
