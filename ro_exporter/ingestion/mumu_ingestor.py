import io
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from PIL import Image

from database import DatabaseManager
from models import Account, Character, DropLog


class MuMuIngestionError(Exception):
    """Custom exception raised for MuMu connection or parsing errors."""

    pass


def find_adb_binary() -> str:
    """Discovers adb.exe across common system and drive paths."""
    # Check system PATH
    try:
        if subprocess.run(["adb", "version"], capture_output=True).returncode == 0:
            return "adb"
    except FileNotFoundError:
        pass

    # High-probability paths based on environment scanning
    candidates = [
        r"E:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe",
        r"E:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
        r"E:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
        r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
        r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c

    # Fallback disk search
    for drive in ["E", "D", "C"]:
        base = Path(f"{drive}:/Program Files/Netease")
        if base.exists():
            for found in base.rglob("adb.exe"):
                return str(found)

    return "adb"


class MuMuLogIngestor:
    """Handles real-time ADB communication, screen capturing, and log ingestion from MuMu Player."""

    DEFAULT_TARGET = "127.0.0.1:16384"

    def __init__(
        self,
        db_manager: DatabaseManager,
        adb_target: str = DEFAULT_TARGET,
        adb_binary: Optional[str] = None,
    ) -> None:
        self.db = db_manager
        self.adb_target = adb_target
        self.adb_bin = adb_binary or find_adb_binary()
        self._is_connected = False
        self.connect_adb()

    def connect_adb(self) -> bool:
        """Establishes an active ADB session to the target MuMu instance."""
        try:
            cmd = [self.adb_bin, "connect", self.adb_target]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if (
                "connected" in res.stdout.lower()
                or "already connected" in res.stdout.lower()
            ):
                self._is_connected = True
                print(
                    f"[MuMu Ingestor] ADB Connected via ({self.adb_bin}) -> {self.adb_target}"
                )
                return True
            print(f"[MuMu Ingestor] Connection warning: {res.stdout.strip()}")
            return False
        except Exception as err:
            raise MuMuIngestionError(
                f"Failed to execute ADB at '{self.adb_bin}': {err}"
            ) from err

    def capture_screenshot(self) -> Image.Image:
        """Captures raw framebuffer screenshot from MuMu Player via ADB."""
        cmd = [self.adb_bin, "-s", self.adb_target, "exec-out", "screencap", "-p"]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0:
            raise MuMuIngestionError(
                f"Screen capture failed: {res.stderr.decode(errors='ignore')}"
            )
        return Image.open(io.BytesIO(res.stdout))

    def parse_log_line(self, line: str, default_char_id: str) -> Optional[DropLog]:
        """Parses raw text log lines into strongly-typed DropLog instances."""
        pattern = r"\[(?P<timestamp>[^\]]+)\]\s+Obtained\s+(?P<item>[^x]+)\s+x(?P<qty>\d+)\s+from\s+(?P<monster>[^\(]+)\((?P<rarity>[^\)]+)\)"
        match = re.search(pattern, line)

        if not match:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                return DropLog(
                    drop_id=None,
                    character_id=default_char_id,
                    item_name=parts[0],
                    rarity=parts[3],
                    quantity=int(parts[1]),
                    monster_name=parts[2],
                    dropped_at=datetime.now(timezone.utc),
                )
            return None

        data = match.groupdict()
        try:
            dt = datetime.fromisoformat(data["timestamp"])
        except ValueError:
            dt = datetime.now(timezone.utc)

        return DropLog(
            drop_id=None,
            character_id=default_char_id,
            item_name=data["item"].strip(),
            rarity=data["rarity"].strip(),
            quantity=int(data["qty"]),
            monster_name=data["monster"].strip(),
            dropped_at=dt,
        )

    def import_exported_file(self, file_path: Path, character_id: str) -> int:
        """Imports drop history log entries from a file into SQLite."""
        if not file_path.exists():
            raise FileNotFoundError(f"Log file does not exist: {file_path}")

        inserted_count = 0
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                drop = self.parse_log_line(line, character_id)
                if drop:
                    self.db.add_drop_log(drop)
                    inserted_count += 1

        print(
            f"[MuMu Ingestor] Inserted {inserted_count} drop records into SQLite database."
        )
        return inserted_count
