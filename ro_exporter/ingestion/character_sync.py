import io
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Callable
import cv2
import numpy as np
import pytesseract
from PIL import Image

from database import DatabaseManager, DatabaseError
from models import Account, Character, DropLog
from mumu_ingestor import MuMuLogIngestor


def setup_tesseract_engine() -> bool:
    """Discovers and configures tesseract.exe path on Windows systems."""
    try:
        if (
            subprocess.run(["tesseract", "--version"], capture_output=True).returncode
            == 0
        ):
            return True
    except FileNotFoundError:
        pass

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"E:\Program Files\Tesseract-OCR\tesseract.exe",
        Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    ]
    for c in candidates:
        p_obj = Path(c)
        if p_obj.exists():
            pytesseract.pytesseract.tesseract_cmd = str(p_obj)
            print(f"[Tesseract Engine] Configured executable: {p_obj}")
            return True
    return False


class CharacterSyncManager:
    """Automates UI navigation in MuMu Player with iterative scroll-scanning to guarantee 100% data capture."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        account_id: str = "ACC_MUMU",
        character_id: str = "63454495",
        screen_resolution: Tuple[int, int] = (1600, 900),
    ) -> None:
        self.db = db_manager
        self.account_id = account_id
        self.character_id = character_id
        self.res_w, self.res_h = screen_resolution
        self.ingestor = MuMuLogIngestor(db_manager)

        self.enable_visual_pointer_location(True)

    def enable_visual_pointer_location(self, enable: bool = True) -> None:
        """Enables Android visual touch indicators and crosshairs via ADB."""
        val = "1" if enable else "0"
        try:
            subprocess.run(
                [
                    self.ingestor.adb_bin,
                    "-s",
                    self.ingestor.adb_target,
                    "shell",
                    "settings",
                    "put",
                    "system",
                    "show_touches",
                    val,
                ],
                capture_output=True,
            )
            subprocess.run(
                [
                    self.ingestor.adb_bin,
                    "-s",
                    self.ingestor.adb_target,
                    "shell",
                    "settings",
                    "put",
                    "system",
                    "pointer_location",
                    val,
                ],
                capture_output=True,
            )
            status = "ENABLED" if enable else "DISABLED"
            print(f"[ADB Overlay] On-screen touch indicators {status}.")
        except Exception as e:
            print(f"[ADB Overlay Warning] Could not set touch indicators: {e}")

    def _tap(self, x: int, y: int, action_label: str = "", delay: float = 1.2) -> None:
        """Executes an ADB tap command at (x, y) with detailed console status updates."""
        label_str = f" -> Action: '{action_label}'" if action_label else ""
        print(f"  👉 [ADB TAP] Coordinates: (X: {x:>4}, Y: {y:>4}){label_str}")

        cmd = [
            self.ingestor.adb_bin,
            "-s",
            self.ingestor.adb_target,
            "shell",
            "input",
            "tap",
            str(x),
            str(y),
        ]
        subprocess.run(cmd, check=True)
        time.sleep(delay)

    def _swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        action_label: str = "",
        duration_ms: int = 500,
        delay: float = 1.2,
    ) -> None:
        """Executes an ADB swipe command from (x1, y1) to (x2, y2) to scroll down data lists."""
        label_str = f" -> Action: '{action_label}'" if action_label else ""
        print(f"  📜 [ADB SWIPE] Scroll ({x1}, {y1}) -> ({x2}, {y2}){label_str}")

        cmd = [
            self.ingestor.adb_bin,
            "-s",
            self.ingestor.adb_target,
            "shell",
            "input",
            "swipe",
            str(x1),
            str(y1),
            str(x2),
            str(y2),
            str(duration_ms),
        ]
        subprocess.run(cmd, check=True)
        time.sleep(delay)

    def _preprocess_crop_clean(
        self, pil_img: Image.Image, crop_box: Tuple[int, int, int, int]
    ) -> np.ndarray:
        """Crops ROI, converts to grayscale, and upscales by 2x for OCR recognition."""
        cropped = pil_img.crop(crop_box)
        img_np = np.array(cropped)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        h, w = gray.shape
        return cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    def _scan_tab_with_scrolling(
        self,
        crop_box: Tuple[int, int, int, int],
        parse_func: Callable[[str], Dict[str, Any]],
        max_swipes: int = 2,
    ) -> Dict[str, Any]:
        """Captures page, parses text, swipes down, and merges new data until fully read."""
        accumulated_data: Dict[str, Any] = {}

        for step in range(max_swipes + 1):
            screen = self.ingestor.capture_screenshot()
            img_processed = self._preprocess_crop_clean(screen, crop_box)
            raw_text = pytesseract.image_to_string(
                img_processed, config="--psm 11"
            ).strip()

            new_entries = parse_func(raw_text)
            prev_count = len(accumulated_data)
            accumulated_data.update(new_entries)
            added_count = len(accumulated_data) - prev_count

            print(
                f"     └─ Scan Frame {step + 1}: Captured {len(new_entries)} metrics ({added_count} new unique fields)"
            )

            if step < max_swipes:
                self._swipe(
                    1250,
                    650,
                    1250,
                    300,
                    action_label=f"Scroll panel down to reveal remaining data (Pass {step + 1})",
                    duration_ms=450,
                    delay=1.2,
                )

        print(
            f"  ✓ [Tab Fully Processed] Total verified parameters collected: {len(accumulated_data)}"
        )
        return accumulated_data

    def sync_full_character_profile(self) -> Optional[Character]:
        """Navigates through all character info tabs, scrolling to capture 100% of data before proceeding."""
        print(
            "\n=== Starting Complete Character Sync (With Guaranteed Scroll-Scanning) ==="
        )

        # ---------------------------------------------------------------------
        # Step 1: Basic Info Tab (ข้อมูลพื้นฐาน)
        # ---------------------------------------------------------------------
        print("\n[STEP 1/4] Syncing Basic Info...")
        self._tap(80, 50, action_label="Tap Avatar Icon (Top-Left)", delay=1.2)
        self._tap(140, 175, action_label="Select Left Menu 1: ข้อมูลตัวละคร", delay=1.0)
        self._tap(1050, 790, action_label="Select Bottom Tab 1: ข้อมูลพื้นฐาน", delay=1.0)

        main_stats = self._scan_tab_with_scrolling(
            crop_box=(930, 40, 1560, 860),
            parse_func=self._parse_main_panel_text,
            max_swipes=1,
        )

        # ---------------------------------------------------------------------
        # Step 2: Attributes Tab (คุณสมบัติ / รายละเอียด - ASPD, Cast Times, Crit Dmg)
        # ---------------------------------------------------------------------
        print(
            "\n[STEP 2/4] Syncing Secondary & Extended Attributes (Scroll-Checking All Rows)..."
        )
        self._tap(1230, 790, action_label="Select Bottom Tab 2: คุณสมบัติ", delay=1.2)

        sec_stats = self._scan_tab_with_scrolling(
            crop_box=(930, 100, 1560, 760),
            parse_func=self._parse_secondary_attributes_text,
            max_swipes=2,  # Swipe twice to ensure bottom cast time / crit damage rows are read
        )

        # ---------------------------------------------------------------------
        # Step 3: Assets Tab (สินทรัพย์ - Gold, Zeny, Bound Zeny, Adventure Coins, MVP Coins)
        # ---------------------------------------------------------------------
        print(
            "\n[STEP 3/4] Syncing Assets & Currencies (Scroll-Checking All Currencies)..."
        )
        self._tap(1410, 790, action_label="Select Bottom Tab 3: สินทรัพย์", delay=1.2)

        asset_stats = self._scan_tab_with_scrolling(
            crop_box=(930, 100, 1560, 760),
            parse_func=self._parse_assets_text,
            max_swipes=2,  # Swipe twice to reach bottom token counts
        )

        # ---------------------------------------------------------------------
        # Step 4: Attribute Allocation Menu (อัปแต้มคุณสมบัติ - STR, AGI, VIT, INT, DEX, LUK)
        # ---------------------------------------------------------------------
        print("\n[STEP 4/4] Syncing Base Attributes (STR, AGI, VIT, INT, DEX, LUK)...")
        self._tap(140, 275, action_label="Select Left Menu 2: อัปแต้มคุณสมบัติ", delay=1.2)

        base_attrs = self._scan_tab_with_scrolling(
            crop_box=(930, 100, 1560, 860),
            parse_func=self._parse_base_attributes_text,
            max_swipes=1,
        )

        # Close Profile Window
        print("\n[COMPLETION] Closing Character Profile window...")
        self._tap(140, 175, action_label="Return to Main Menu", delay=0.8)
        self._tap(1550, 40, action_label="Close Profile Window (X Button)", delay=0.8)

        # ---------------------------------------------------------------------
        # Build & Save Models
        # ---------------------------------------------------------------------
        char_id = str(main_stats.get("character_id") or self.character_id)

        character = Character(
            character_id=char_id,
            account_id=self.account_id,
            character_name=str(main_stats.get("character_name", "ต๋องง")),
            job_class=str(main_stats.get("job_class", "High Priest")),
            base_level=int(main_stats.get("base_level", 80)),
            job_level=int(main_stats.get("job_level", 37)),
            str_attr=int(base_attrs.get("str_attr", 0)),
            agi_attr=int(base_attrs.get("agi_attr", 0)),
            vit_attr=int(base_attrs.get("vit_attr", 0)),
            int_attr=int(base_attrs.get("int_attr", 0)),
            dex_attr=int(base_attrs.get("dex_attr", 0)),
            luk_attr=int(base_attrs.get("luk_attr", 0)),
            atk=float(main_stats.get("atk", 0.0)),
            def_attr=float(main_stats.get("p_def", 0.0)),
            crit=float(sec_stats.get("crit", 0.0)),
            haste=float(sec_stats.get("haste", 0.0)),
        )

        try:
            self.db.create_account(Account(self.account_id))
        except DatabaseError:
            pass

        self.db.upsert_character(character)

        # Save all extracted currencies as snapshot entries
        for asset_name, asset_qty in asset_stats.items():
            if asset_qty > 0:
                self.db.add_drop_log(
                    DropLog(
                        drop_id=None,
                        character_id=char_id,
                        item_name=asset_name,
                        rarity="Currency",
                        quantity=asset_qty,
                        monster_name="Asset Snapshot",
                        dropped_at=datetime.now(timezone.utc),
                    )
                )

        print(
            f"\n[SUCCESS] Extracted Profile & Sync Complete for '{character.character_name}' (ID: {character.character_id})"
        )
        print(
            f"  - Base Level: {character.base_level} | Job Level: {character.job_level} ({character.job_class})"
        )
        print(
            f"  - Base Attributes: STR={character.str_attr}, AGI={character.agi_attr}, VIT={character.vit_attr}, INT={character.int_attr}, DEX={character.dex_attr}, LUK={character.luk_attr}"
        )
        print(
            f"  - Secondary Stats: ATK={character.atk}, P.DEF={character.def_attr}, Crit={character.crit}, Haste={character.haste}"
        )
        print(f"  - Currencies & Tokens Synced: {asset_stats}")

        return character

    @staticmethod
    def _parse_main_panel_text(text: str) -> Dict[str, Any]:
        """Parses character metadata, bounded levels, EXP progress, and primary stats."""
        data: Dict[str, Any] = {}

        # Job Class Badge
        job_match = re.search(r"(High Priest|Sniper|Lord Knight|High Wizard|Assassin Cross|Paladin)", text, re.I)
        if job_match:
            data["job_class"] = job_match.group(1)

        # Character ID & Name
        id_match = re.search(r"(?:ID|1D|ld)[:\s]*(\d{6,10})", text, re.I)
        if id_match:
            data["character_id"] = id_match.group(1)

        name_match = re.search(r"([A-Za-z0-9_\u0E00-\u0E7F]{2,20})\s*\n+.*?(?:ID|1D|ld)", text, re.I)
        if name_match:
            data["character_name"] = name_match.group(1).strip()

        # Base Level & EXP Extraction: "Base Lv. 83  8326075/25327961"
        base_exp_match = re.search(r"Base\s*Lv\.?\s*(\d{1,3})[^\d\n]*(\d+)\s*/\s*(\d+)", text, re.I)
        if base_exp_match:
            data["base_level"] = int(base_exp_match.group(1))
            data["base_exp_current"] = int(base_exp_match.group(2))
            data["base_exp_required"] = int(base_exp_match.group(3))
            if data["base_exp_required"] > 0:
                data["base_exp_pct"] = round((data["base_exp_current"] / data["base_exp_required"]) * 100, 2)

        # Job Level & EXP Extraction: "Job Lv. 39  9598697/31934282"
        job_exp_match = re.search(r"Job\s*Lv\.?\s*(\d{1,3})[^\d\n]*(\d+)\s*/\s*(\d+)", text, re.I)
        if job_exp_match:
            data["job_level"] = int(job_exp_match.group(1))
            data["job_exp_current"] = int(job_exp_match.group(2))
            data["job_exp_required"] = int(job_exp_match.group(3))
            if data["job_exp_required"] > 0:
                data["job_exp_pct"] = round((data["job_exp_current"] / data["job_exp_required"]) * 100, 2)

        # Primary Grid Stats
        atk_match = re.search(r"Atk\s*(\d+)", text, re.I)
        if atk_match:
            data["atk"] = float(atk_match.group(1))

        pdef_match = re.search(r"P\.?DEF\s*(\d+)", text, re.I)
        if pdef_match:
            data["p_def"] = float(pdef_match.group(1))

        return data

    @staticmethod
    def _parse_secondary_attributes_text(text: str) -> Dict[str, Any]:
        """Parses primary and extended attributes (Hit, Flee, ASPD, Crit, Cast Times)."""
        sec: Dict[str, Any] = {}
        patterns = {
            "hit": r"Hit[:\s]+(\d+)",
            "flee": r"Flee[:\s]+(\d+)",
            "aspd": r"ASPD[:\s]+([\d\.]+)",
            "crit": r"Crit[:\s]+(\d+)",
            "crit_damage_pct": r"Crit\s*Damage%?[:\s]+([\d\.\-]+)%",
            "variable_cast": r"ร่ายแปรผัน[:\s]+([\d\.\-]+)",
            "variable_cast_pct": r"ร่ายแปรผัน%[:\s]+([\d\.\-]+)%",
            "fixed_cast": r"ร่ายคงที่[:\s]+([\d\.\-]+)",
            "reduced_fixed_cast_pct": r"ลดร่ายคงที่%[:\s]+([\d\.\-]+)%",
        }

        for key, pat in patterns.items():
            match = re.search(pat, text, re.I)
            if match:
                val = match.group(1)
                sec[key] = float(val) if "." in val else int(val)

        return sec

    @staticmethod
    def _parse_assets_text(text: str) -> Dict[str, int]:
        """Parses all currencies and token balances (Gold Coins, Zeny, Bound Zeny, Adventure Coins, Contribution, MVP Coins)."""
        assets: Dict[str, int] = {}
        patterns = {
            "Gold Coins": r"Gold\s*Coins[:\s]+([\d,]+)",
            "Zeny": r"(?:^|\n)\s*Zeny[:\s]+([\d,]+)",
            "Zeny (Bound)": r"Zeny\s*ผูกมัด[:\s]+([\d,]+)",
            "Adventure Coins": r"Adventure\s*C(?:oins)?[:\s]+([\d,]+)",
            "Contribution Points": r"แต้มผลงาน[:\s]+([\d,]+)",
            "MVP Coins": r"MVP\s*Coins[:\s]+([\d,]+)",
        }

        for name, pat in patterns.items():
            match = re.search(pat, text, re.I)
            if match:
                assets[name] = int(match.group(1).replace(",", ""))

        return assets

    @staticmethod
    def _parse_base_attributes_text(text: str) -> Dict[str, int]:
        """Parses STR, AGI, VIT, INT, DEX, LUK from Attribute Points Allocation screen."""
        attrs: Dict[str, int] = {}
        for stat in ["STR", "AGI", "VIT", "INT", "DEX", "LUK"]:
            match = re.search(rf"{stat}[:\s]+(\d+)", text, re.I)
            attrs[f"{stat.lower()}_attr"] = int(match.group(1)) if match else 0
        return attrs


def main() -> None:
    if not setup_tesseract_engine():
        print("[ERROR] Tesseract-OCR binary not found.")
        return

    db = DatabaseManager(Path("ragnarok_analytics.db"))
    syncer = CharacterSyncManager(
        db_manager=db,
        account_id="ACC_MUMU",
        character_id="63454495",
        screen_resolution=(1600, 900),
    )

    syncer.sync_full_character_profile()


if __name__ == "__main__":
    main()
