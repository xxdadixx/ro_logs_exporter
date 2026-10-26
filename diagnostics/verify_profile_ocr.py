import cv2
import numpy as np
import pytesseract
import re
import subprocess
from pathlib import Path
from PIL import Image
from mumu_ingestor import MuMuLogIngestor
from database import DatabaseManager


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


def preprocess_card_image(pil_img: Image.Image, crop_box: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """
    Generates two preprocessed image variations:
    1. Standard CLAHE Grayscale (for general text & grid stats)
    2. Binary Threshold Inversion (for orange/blue level bars)
    """
    cropped = pil_img.crop(crop_box)
    img_np = np.array(cropped)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # 1. CLAHE Contrast Upscaled Image
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    h, w = enhanced.shape
    enhanced_upscaled = cv2.resize(enhanced, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    # 2. Binary Threshold Image (Sharpens white numbers inside orange progress bars)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    thresh_upscaled = cv2.resize(thresh, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    return enhanced_upscaled, thresh_upscaled


def inspect_live_profile() -> None:
    setup_tesseract_engine()
    db = DatabaseManager(Path("ragnarok_analytics.db"))
    ingestor = MuMuLogIngestor(db)

    print("=== Capturing Frame & Verifying Profile OCR Accuracy ===")
    screen = ingestor.capture_screenshot()

    # Crop Right Info Card Panel (930, 40, 1560, 860)
    card_crop = (930, 40, 1560, 860)
    img_enhanced, img_thresh = preprocess_card_image(screen, card_crop)

    # Perform dual-pass OCR reads
    raw_text = pytesseract.image_to_string(img_enhanced, config="--psm 11").strip()
    raw_text_thresh = pytesseract.image_to_string(img_thresh, config="--psm 11").strip()

    parsed = {}

    # 1. Character Name (Line directly preceding ID/1D)
    name_match = re.search(r"([A-Za-z0-9_\u0E00-\u0E7F]{2,20})\s*\n+.*?(?:ID|1D|ld)", raw_text, re.I)
    if name_match:
        parsed["name"] = name_match.group(1).strip()

    # 2. Character ID (Handles ID: or 1D:)
    id_match = re.search(r"(?:ID|1D|ld)[:\s]*(\d{6,10})", raw_text, re.I)
    if id_match:
        parsed["id"] = id_match.group(1)

    # 3. Guild Name
    guild_match = re.search(r"Guild\s+([A-Za-z0-9_\u0E00-\u0E7F]+)", raw_text, re.I)
    if guild_match:
        parsed["guild"] = guild_match.group(1)

    # 4. Job Class Badge
    job_match = re.search(r"(High Priest|Sniper|Lord Knight|High Wizard|Assassin Cross|Paladin)", raw_text, re.I)
    if job_match:
        parsed["job_class"] = job_match.group(1)

    # 5. Base Level & Job Level (Checks both OCR passes for numbers on progress bars)
    combined_text = raw_text + "\n" + raw_text_thresh

    base_lvl = re.search(r"Base\s*Lv\.?\s*(\d{1,3})", combined_text, re.I)
    if base_lvl:
        parsed["base_lvl"] = int(base_lvl.group(1))

    job_lvl = re.search(r"Job\s*Lv\.?\s*(\d{1,3})", combined_text, re.I)
    if job_lvl:
        parsed["job_lvl"] = int(job_lvl.group(1))

    # 6. Primary Grid Stats (HP, MP, ATK, P.DEF, M.ATK, M.DEF)
    hp_match = re.search(r"HP[^\d\n]*(\d+)", raw_text, re.I)
    if hp_match:
        parsed["hp"] = int(hp_match.group(1))

    mp_match = re.search(r"MP[^\d\n]*(\d+)", raw_text, re.I)
    if mp_match:
        parsed["mp"] = int(mp_match.group(1))

    atk_match = re.search(r"Atk\s*(\d+)", raw_text, re.I)
    if atk_match:
        parsed["atk"] = int(atk_match.group(1))

    pdef_match = re.search(r"P\.?DEF\s*(\d+)", raw_text, re.I)
    if pdef_match:
        parsed["p_def"] = int(pdef_match.group(1))

    matk_match = re.search(r"M\.?ATK\s*(\d+)", raw_text, re.I)
    if matk_match:
        parsed["m_atk"] = int(matk_match.group(1))

    mdef_match = re.search(r"M\.?DEF\s*(\d+)", raw_text, re.I)
    if mdef_match:
        parsed["m_def"] = int(mdef_match.group(1))

    print("=== VERIFIED PARSED PROFILE METRICS ===")
    for k, v in parsed.items():
        print(f"  - {k:<12}: {v}")


if __name__ == "__main__":
    inspect_live_profile()