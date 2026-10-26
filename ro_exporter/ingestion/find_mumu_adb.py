import os
import subprocess
from pathlib import Path
from typing import Optional


def find_adb_executable() -> Optional[Path]:
    """Scans system environment and local drive paths for adb.exe."""
    # 1. Check if adb is already in system PATH
    try:
        res = subprocess.run(["adb", "version"], capture_output=True, text=True)
        if res.returncode == 0:
            return Path("adb")
    except FileNotFoundError:
        pass

    # 2. Search common installation drives for MuMu's embedded adb.exe
    candidate_paths = [
        r"E:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
        r"E:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
        r"E:\Program Files\Netease\MuMuPlayer\shell\adb.exe",
        r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
        r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
    ]

    for p in candidate_paths:
        path_obj = Path(p)
        if path_obj.exists():
            return path_obj

    # 3. Dynamic disk drive fallback search
    for drive in ["E", "D", "C"]:
        base_dir = Path(f"{drive}:/Program Files/Netease")
        if base_dir.exists():
            for found_adb in base_dir.rglob("adb.exe"):
                return found_adb

    return None


def verify_mumu_connection() -> None:
    adb_bin = find_adb_executable()
    if not adb_bin:
        print("[ERROR] Could not find adb.exe on any drive (C:, E:, D:).")
        return

    print(f"[FOUND ADB] Located binary at: {adb_bin}")

    # Ports listed in your MuMu diagnosis screen
    ports = [16384, 5555]
    connected = False

    for port in ports:
        target = f"127.0.0.1:{port}"
        print(f"Attempting ADB connection to {target}...")
        cmd = [str(adb_bin), "connect", target]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if "connected" in result.stdout.lower() or "already connected" in result.stdout.lower():
            print(f"[SUCCESS] Connected to MuMu Player via {target}!")
            connected = True
            break

    if connected:
        devices_res = subprocess.run([str(adb_bin), "devices"], capture_output=True, text=True)
        print("\nActive ADB Devices:")
        print(devices_res.stdout.strip())
    else:
        print("[ERROR] Failed to establish connection on active ports.")


if __name__ == "__main__":
    verify_mumu_connection()