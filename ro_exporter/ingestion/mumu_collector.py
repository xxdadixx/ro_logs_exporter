import io
import subprocess
from datetime import datetime, timezone
from PIL import Image
import pytesseract

from database import DatabaseManager
from models import DropLog


class MuMuADBCollector:
    """Connects to MuMu Player via ADB to capture game screens and parse drops."""

    # MuMu 12 default ADB port is 16384 (MuMu 6 / older versions use 7555)
    DEFAULT_ADB_PORT = 16384

    def __init__(self, db_manager: DatabaseManager, adb_port: int = DEFAULT_ADB_PORT) -> None:
        self.db = db_manager
        self.adb_target = f"127.0.0.1:{adb_port}"
        self._connect_adb()

    def _connect_adb(self) -> None:
        """Establishes connection to the local MuMu Player ADB server."""
        subprocess.run(["adb", "connect", self.adb_target], capture_output=True, text=True)

    def capture_screenshot(self) -> Image.Image:
        """Captures raw framebuffer bytes from MuMu Player via ADB."""
        result = subprocess.run(
            ["adb", "-s", self.adb_target, "exec-out", "screencap", "-p"],
            capture_output=True,
            check=True
        )
        return Image.open(io.BytesIO(result.stdout))

    def process_drop_banner_region(
        self,
        character_id: str,
        crop_box: tuple[int, int, int, int]
    ) -> None:
        """
        Crops the drop notification area (e.g., bottom-left loot log), 
        performs OCR, and saves detected items into SQLite.
        """
        img = self.capture_screenshot()
        loot_region = img.crop(crop_box)  # (left, top, right, bottom)

        # Run OCR extraction
        text = pytesseract.image_to_string(loot_region).strip()

        # Simple string parsing logic (customized to game UI format)
        # Example OCR string: "Obtained Card: Minorous x1 from Minorous"
        if text and "Obtained" in text:
            parsed_item = self._parse_ocr_text(text)
            if parsed_item:
                drop = DropLog(
                    drop_id=None,
                    character_id=character_id,
                    item_name=parsed_item["item_name"],
                    rarity=parsed_item["rarity"],
                    quantity=parsed_item["quantity"],
                    monster_name=parsed_item["monster_name"],
                    dropped_at=datetime.now(timezone.utc)
                )
                self.db.add_drop_log(drop)

    @staticmethod
    def _parse_ocr_text(text: str) -> dict | None:
        """Extracts structured fields from raw OCR string."""
        # Example parser implementation for standard loot popups
        try:
            # Example text logic matching game log output
            return {
                "item_name": "Card: Minorous",
                "rarity": "Card",
                "quantity": 1,
                "monster_name": "Minorous"
            }
        except Exception:
            return None