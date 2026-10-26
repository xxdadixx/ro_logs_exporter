import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set
import cv2
import numpy as np
import pytesseract
from PIL import Image

from database import DatabaseManager, DatabaseError
from exporter import ExcelExporter
from models import Account, Character, DropLog
from mumu_ingestor import MuMuLogIngestor


def setup_tesseract_path() -> bool:
    """Finds and configures tesseract.exe path on Windows systems."""
    # Check system PATH first
    try:
        if (
            subprocess.run(["tesseract", "--version"], capture_output=True).returncode
            == 0
        ):
            return True
    except FileNotFoundError:
        pass

    # Common installation paths on Windows
    candidate_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"E:\Program Files\Tesseract-OCR\tesseract.exe",
        Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    ]

    for p in candidate_paths:
        p_obj = Path(p)
        if p_obj.exists():
            pytesseract.pytesseract.tesseract_cmd = str(p_obj)
            print(f"[Tesseract OCR] Located engine binary at: {p_obj}")
            return True

    return False


class MuMuDropScanner:
    """Continuously captures emulator screens, parses loot text via OCR, and logs drops."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        character_id: str,
        # Default ROI optimized for 1600x900 screen resolution
        crop_box: tuple[int, int, int, int] = (350, 150, 1250, 350),
        scan_interval: float = 1.5,
    ) -> None:
        self.db = db_manager
        self.char_id = character_id
        self.crop_box = crop_box  # (left, top, right, bottom)
        self.scan_interval = scan_interval
        self.ingestor = MuMuLogIngestor(db_manager)
        self.processed_signatures: Set[str] = set()

    def preprocess_image(self, pil_img: Image.Image) -> np.ndarray:
        """Crops screen region and applies grayscale thresholding for OCR text extraction."""
        cropped = pil_img.crop(self.crop_box)
        img_np = np.array(cropped)

        # Convert RGB to Grayscale
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        # Threshold image for text contrast
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def scan_once(self) -> Optional[DropLog]:
        """Captures frame, runs OCR, and records new drop event."""
        raw_screen = self.ingestor.capture_screenshot()
        processed_img = self.preprocess_image(raw_screen)

        # Extract text using Tesseract
        raw_text = pytesseract.image_to_string(processed_img, config="--psm 6").strip()

        if not raw_text:
            return None

        # Prevent logging duplicate frames
        sig = raw_text.lower()
        if sig in self.processed_signatures:
            return None

        drop = self.ingestor.parse_log_line(raw_text, self.char_id)
        if drop:
            self.db.add_drop_log(drop)
            self.processed_signatures.add(sig)
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] LOGGED DROP: {drop.item_name} x{drop.quantity} from {drop.monster_name}"
            )
            return drop

        return None

    def start_scanner(self) -> None:
        """Runs the continuous OCR scanning loop."""
        print(f"=== Starting Live OCR Drop Scanner for Character: {self.char_id} ===")
        print(f"Crop Window (left, top, right, bottom): {self.crop_box}")
        print("Press Ctrl+C to stop scanning and export Excel report.\n")

        try:
            while True:
                self.scan_once()
                time.sleep(self.scan_interval)
        except KeyboardInterrupt:
            print("\nScanner stopped by user.")
            print("Exporting final analytics report...")
            exporter = ExcelExporter(self.db)
            exporter.export_full_workbook("Ragnarok_Live_Drops.xlsx")
            print("Export complete -> Ragnarok_Live_Drops.xlsx")


if __name__ == "__main__":
    if not setup_tesseract_path():
        print("[ERROR] Tesseract-OCR binary not found.")
        print(
            "Please install Tesseract-OCR for Windows from https://github.com/UB-Mannheim/tesseract/wiki"
        )
        exit(1)

    db = DatabaseManager("ragnarok_analytics.db")

    # Safely ensure account exists
    try:
        db.create_account(Account("ACC_MUMU"))
    except DatabaseError:
        pass  # Account already exists in database

    # Upsert character profile (handles updates smoothly)
    db.upsert_character(
        Character(
            character_id="CHAR_LIVE_01",
            account_id="ACC_MUMU",
            character_name="ActiveFarmer",
            job_class="Sniper",
            base_level=90,
            job_level=50,
            str_attr=10,
            agi_attr=90,
            vit_attr=20,
            int_attr=10,
            dex_attr=100,
            luk_attr=30,
            atk=2800.0,
            def_attr=350.0,
            crit=60.0,
            haste=900.0,
        )
    )

    # ROI bounding box tuned for 1600x900 resolution
    scanner = MuMuDropScanner(
        db_manager=db,
        character_id="CHAR_LIVE_01",
        crop_box=(350, 150, 1250, 350),
        scan_interval=1.0,
    )
    scanner.start_scanner()
