from database import DatabaseManager
from mumu_ingestor import MuMuLogIngestor
from pathlib import Path

def test_live_screen():
    db = DatabaseManager(Path("ragnarok_analytics.db"))
    ingestor = MuMuLogIngestor(db)
    
    print("Capturing live screenshot from MuMu Player...")
    img = ingestor.capture_screenshot()
    
    output_png = Path("mumu_live_capture.png")
    img.save(output_png)
    print(f"SUCCESS: Captured game screen ({img.width}x{img.height}) -> saved to {output_png.resolve()}")

if __name__ == "__main__":
    test_live_screen()