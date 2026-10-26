# Updated imports for main.py / run_mumu_pipeline.py
from ro_exporter.core.database import DatabaseManager, DatabaseError
from ro_exporter.core.models import Account, Character, DropLog
from ro_exporter.core.analytics import AnalyticsController
from ro_exporter.core.exporter import ExcelExporter
from ro_exporter.ingestion.mumu_ingestor import MuMuLogIngestor
from ro_exporter.ingestion.character_sync import CharacterSyncManager

from pathlib import Path
from database import DatabaseManager
from analytics import AnalyticsController
from exporter import ExcelExporter
from models import Account, Character
from mumu_ingestor import MuMuLogIngestor


def main() -> None:
    db_file = Path("ragnarok_analytics.db")
    db = DatabaseManager(db_file)
    ingestor = MuMuLogIngestor(db)

    print("=== Ragnarok: The New World — MuMu Player Integration Pipeline ===")

    # 1. Register Account and Active Alt Character
    acc_id = "ACC_MUMU_01"
    char_id = "CHAR_MUMU_SNIPER"
    
    db.create_account(Account(account_id=acc_id))
    db.upsert_character(Character(
        character_id=char_id,
        account_id=acc_id,
        character_name="MuMuSniperPro",
        job_class="Sniper",
        base_level=95, job_level=60,
        str_attr=10, agi_attr=99, vit_attr=30, int_attr=10, dex_attr=120, luk_attr=50,
        atk=3600.0, def_attr=450.0, crit=80.0, haste=1200.0
    ))

    # 2. Setup Sample Log File in MuMu Shared Directory
    shared_dir = Path.home() / "Documents" / "MuMuShared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    sample_log_file = shared_dir / "ro_drops_export.txt"

    # Seed sample exported log lines matching emulator output format
    sample_log_content = (
        "[2026-03-30 14:00:00] Obtained Card: Minorous x1 from Minorous (Card)\n"
        "[2026-03-30 14:05:12] Obtained Oridecon x10 from Minorous (Material)\n"
        "[2026-03-30 14:12:45] Obtained Elunium x15 from Skeleton Worker (Material)\n"
        "[2026-03-30 14:20:30] Obtained Bow of Gale x1 from Anubis (Equipment)\n"
    )
    sample_log_file.write_text(sample_log_content, encoding="utf-8")

    # 3. Import Data via Ingestor
    print(f"\n[1/3] Ingesting drop log file from MuMu shared directory...")
    ingestor.import_exported_file(sample_log_file, character_id=char_id)

    # 4. Generate Analytics Summary
    analytics = AnalyticsController(db)
    top_items = analytics.get_top_items(limit=5)
    
    print("\n[2/3] Integrated Analytics Snapshot:")
    for item in top_items:
        print(f"  - Item: {item['item_name']:<25} | Qty: {item['total_quantity']:<5} | Category: {item['rarity']}")

    # 5. Export Workbook
    print("\n[3/3] Exporting integrated results to Excel...")
    exporter = ExcelExporter(db)
    output_path = Path("Ragnarok_MuMu_Report.xlsx")
    exporter.export_full_workbook(output_path)
    print(f"SUCCESS: Report saved to {output_path.resolve()}")


if __name__ == "__main__":
    main()