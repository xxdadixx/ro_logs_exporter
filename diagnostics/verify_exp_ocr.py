import cv2
import numpy as np
import pytesseract
import re
from pathlib import Path
from PIL import Image
from database import DatabaseManager
from mumu_ingestor import MuMuLogIngestor


def setup_tesseract_engine() -> bool:
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"E:\Program Files\Tesseract-OCR\tesseract.exe",
        Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            pytesseract.pytesseract.tesseract_cmd = str(c)
            return True
    return False


def test_exp_extraction() -> None:
    setup_tesseract_engine()
    db = DatabaseManager(Path("ragnarok_analytics.db"))
    ingestor = MuMuLogIngestor(db)

    print("=== Capturing Frame & Testing Multiline EXP Extraction ===")
    screen = ingestor.capture_screenshot()

    # Crop Level & EXP region on right card panel (X: 930 to 1560, Y: 300 to 520)
    exp_crop = screen.crop((930, 300, 1560, 520))
    img_np = np.array(exp_crop)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # 2x Upscaling with CLAHE Contrast
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    h, w = enhanced.shape
    upscaled = cv2.resize(enhanced, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    raw_text = pytesseract.image_to_string(upscaled, config="--psm 11").strip()

    print("\n--- RAW OCR TEXT IN EXP REGION ---")
    print(raw_text)
    print("----------------------------------\n")

    # 1. Primary Strategy: Multiline-aware pattern (allows newlines between level and EXP)
    base_match = re.search(
        r"Base\s*Lv\.?\s*(\d{1,3})[\s\S]*?(\d{6,9})\s*[/|]\s*(\d{6,9})", raw_text, re.I
    )
    job_match = re.search(
        r"Job\s*Lv\.?\s*(\d{1,3})[\s\S]*?(\d{6,9})\s*[/|]\s*(\d{6,9})", raw_text, re.I
    )

    # 2. Fallback Strategy: Extract all 6-to-9 digit fraction pairs (XXXXXXX/YYYYYYYY)
    fraction_matches = re.findall(r"(\d{6,9})\s*[/|]\s*(\d{6,9})", raw_text)

    # Parse Base EXP
    base_lvl, base_curr, base_req = None, None, None
    if base_match:
        base_lvl = int(base_match.group(1))
        base_curr = int(base_match.group(2))
        base_req = int(base_match.group(3))
    elif len(fraction_matches) >= 1:
        base_curr = int(fraction_matches[0][0])
        base_req = int(fraction_matches[0][1])
        # Extract level from standalone match
        lvl_m = re.search(r"Base\s*Lv\.?\s*(\d{1,3})", raw_text, re.I)
        base_lvl = int(lvl_m.group(1)) if lvl_m else 83

    # Parse Job EXP
    job_lvl, job_curr, job_req = None, None, None
    if job_match:
        job_lvl = int(job_match.group(1))
        job_curr = int(job_match.group(2))
        job_req = int(job_match.group(3))
    elif len(fraction_matches) >= 2:
        job_curr = int(fraction_matches[1][0])
        job_req = int(fraction_matches[1][1])
        lvl_m = re.search(r"Job\s*Lv\.?\s*(\d{1,3})", raw_text, re.I)
        job_lvl = int(lvl_m.group(1)) if lvl_m else 39

    print("=== EXP & LEVEL EXTRACTION RESULTS ===")
    if base_curr and base_req:
        pct = round((base_curr / base_req) * 100, 2)
        print(f"  Base Level     : Lv. {base_lvl if base_lvl else 'N/A'}")
        print(f"  Base EXP       : {base_curr:,} / {base_req:,}")
        print(f"  Base Progress  : {pct}%")
    else:
        print("  Base EXP       : [Failed to parse Base EXP line]")

    if job_curr and job_req:
        pct = round((job_curr / job_req) * 100, 2)
        print(f"\n  Job Level      : Lv. {job_lvl if job_lvl else 'N/A'}")
        print(f"  Job EXP        : {job_curr:,} / {job_req:,}")
        print(f"  Job Progress   : {pct}%")
    else:
        print("  Job EXP        : [Failed to parse Job EXP line]")


if __name__ == "__main__":
    test_exp_extraction()
