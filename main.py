import argparse
import csv
import json

# Updated imports for main.py / run_mumu_pipeline.py
from ro_exporter.core.database import DatabaseManager, DatabaseError
from ro_exporter.core.models import Account, Character, DropLog
from ro_exporter.core.analytics import AnalyticsController
from ro_exporter.core.exporter import ExcelExporter
from ro_exporter.ingestion.mumu_ingestor import MuMuLogIngestor
from ro_exporter.ingestion.character_sync import CharacterSyncManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from analytics import AnalyticsController
from database import DatabaseManager
from exporter import ExcelExporter, ExportError
from models import Account, Character, DropLog


def seed_demo_data(db: DatabaseManager) -> None:
    """Populates initial database state with hardcoded demo data."""
    acc1 = Account(account_id="ACC_10091")
    acc2 = Account(account_id="ACC_10092")
    db.create_account(acc1)
    db.create_account(acc2)

    char1 = Character(
        character_id="CHAR_SNIPER_01",
        account_id="ACC_10091",
        character_name="ValkyrieAim",
        job_class="Sniper",
        base_level=95,
        job_level=60,
        str_attr=10,
        agi_attr=99,
        vit_attr=30,
        int_attr=10,
        dex_attr=120,
        luk_attr=50,
        atk=3450.5,
        def_attr=420.0,
        crit=78.5,
        haste=1120.0,
    )

    char2 = Character(
        character_id="CHAR_HW_01",
        account_id="ACC_10091",
        character_name="Pyromancer",
        job_class="High Wizard",
        base_level=92,
        job_level=55,
        str_attr=5,
        agi_attr=20,
        vit_attr=45,
        int_attr=125,
        dex_attr=80,
        luk_attr=10,
        atk=4100.0,
        def_attr=380.0,
        crit=5.0,
        haste=2450.0,
    )

    char3 = Character(
        character_id="CHAR_LK_01",
        account_id="ACC_10092",
        character_name="IronGuard",
        job_class="Lord Knight",
        base_level=98,
        job_level=65,
        str_attr=110,
        agi_attr=50,
        vit_attr=100,
        int_attr=1,
        dex_attr=40,
        luk_attr=20,
        atk=3890.0,
        def_attr=950.5,
        crit=15.0,
        haste=400.0,
    )

    db.upsert_character(char1)
    db.upsert_character(char2)
    db.upsert_character(char3)

    drops = [
        DropLog(
            None,
            "CHAR_SNIPER_01",
            "Card: Skeleton Worker",
            "Card",
            1,
            "Skeleton Worker",
        ),
        DropLog(None, "CHAR_SNIPER_01", "Oridecon", "Material", 15, "Minorous"),
        DropLog(None, "CHAR_SNIPER_01", "Elunium", "Material", 22, "Minorous"),
        DropLog(None, "CHAR_HW_01", "Staff of Wing", "Equipment", 1, "Anubis"),
        DropLog(None, "CHAR_HW_01", "Zargon", "Normal", 140, "Requiem"),
        DropLog(None, "CHAR_LK_01", "Card: Pasana", "Card", 1, "Pasana"),
        DropLog(None, "CHAR_LK_01", "Oridecon", "Material", 38, "Pasana"),
    ]

    for d in drops:
        db.add_drop_log(d)


def import_json_data(db: DatabaseManager, json_path: Path) -> None:
    """Imports accounts, characters, and drops from a structured JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Accounts
    existing_accounts = set()
    for acc_data in data.get("accounts", []):
        acc = Account(account_id=str(acc_data["account_id"]))
        db.create_account(acc)
        existing_accounts.add(acc.account_id)

    # 2. Characters
    for c in data.get("characters", []):
        acc_id = str(c["account_id"])
        if acc_id not in existing_accounts:
            db.create_account(Account(account_id=acc_id))
            existing_accounts.add(acc_id)

        char = Character(
            character_id=str(c["character_id"]),
            account_id=acc_id,
            character_name=str(c["character_name"]),
            job_class=str(c["job_class"]),
            base_level=int(c["base_level"]),
            job_level=int(c["job_level"]),
            str_attr=int(c.get("str_attr", 0)),
            agi_attr=int(c.get("agi_attr", 0)),
            vit_attr=int(c.get("vit_attr", 0)),
            int_attr=int(c.get("int_attr", 0)),
            dex_attr=int(c.get("dex_attr", 0)),
            luk_attr=int(c.get("luk_attr", 0)),
            atk=float(c.get("atk", 0.0)),
            def_attr=float(c.get("def_attr", 0.0)),
            crit=float(c.get("crit", 0.0)),
            haste=float(c.get("haste", 0.0)),
        )
        db.upsert_character(char)

    # 3. Drop Logs
    for d in data.get("drops", []):
        dropped_at = (
            datetime.fromisoformat(d["dropped_at"].replace("Z", "+00:00"))
            if "dropped_at" in d
            else datetime.now(timezone.utc)
        )
        drop = DropLog(
            drop_id=None,
            character_id=str(d["character_id"]),
            item_name=str(d["item_name"]),
            rarity=str(d["rarity"]),
            quantity=int(d["quantity"]),
            monster_name=str(d["monster_name"]),
            dropped_at=dropped_at,
        )
        db.add_drop_log(drop)


def import_csv_data(
    db: DatabaseManager,
    char_csv_path: Optional[Path] = None,
    drop_csv_path: Optional[Path] = None,
) -> None:
    """Imports characters and drops from separate CSV files."""
    created_accounts = set()

    # Load Characters CSV
    if char_csv_path and char_csv_path.exists():
        with open(char_csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for c in reader:
                acc_id = str(c["account_id"])
                if acc_id not in created_accounts:
                    db.create_account(Account(account_id=acc_id))
                    created_accounts.add(acc_id)

                char = Character(
                    character_id=str(c["character_id"]),
                    account_id=acc_id,
                    character_name=str(c["character_name"]),
                    job_class=str(c["job_class"]),
                    base_level=int(c["base_level"]),
                    job_level=int(c["job_level"]),
                    str_attr=int(c.get("str_attr", 0)),
                    agi_attr=int(c.get("agi_attr", 0)),
                    vit_attr=int(c.get("vit_attr", 0)),
                    int_attr=int(c.get("int_attr", 0)),
                    dex_attr=int(c.get("dex_attr", 0)),
                    luk_attr=int(c.get("luk_attr", 0)),
                    atk=float(c.get("atk", 0.0)),
                    def_attr=float(c.get("def_attr", 0.0)),
                    crit=float(c.get("crit", 0.0)),
                    haste=float(c.get("haste", 0.0)),
                )
                db.upsert_character(char)

    # Load Drops CSV
    if drop_csv_path and drop_csv_path.exists():
        with open(drop_csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for d in reader:
                dropped_at = (
                    datetime.fromisoformat(d["dropped_at"].replace("Z", "+00:00"))
                    if d.get("dropped_at")
                    else datetime.now(timezone.utc)
                )
                drop = DropLog(
                    drop_id=None,
                    character_id=str(d["character_id"]),
                    item_name=str(d["item_name"]),
                    rarity=str(d["rarity"]),
                    quantity=int(d["quantity"]),
                    monster_name=str(d["monster_name"]),
                    dropped_at=dropped_at,
                )
                db.add_drop_log(drop)


def print_table(
    title: str, headers: List[str], rows: List[List[Any]], col_widths: List[int]
) -> None:
    """Utility function to render formatted ASCII tables in the console."""
    divider = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    print(f"\n{title}")
    print(divider)
    header_str = (
        "| " + " | ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers)) + " |"
    )
    print(header_str)
    print(divider)

    for row in rows:
        formatted_cells = []
        for i, val in enumerate(row):
            w = col_widths[i]
            if isinstance(val, (int, float)):
                formatted_cells.append(f"{val:>{w}}")
            else:
                formatted_cells.append(f"{str(val):<{w}}")
        print("| " + " | ".join(formatted_cells) + " |")

    print(divider)


def print_console_analytics(
    analytics: AnalyticsController, db: DatabaseManager
) -> None:
    """Fetches analytics data and prints structured console tables."""
    characters = db.get_all_characters_with_account()
    char_headers = [
        "Account ID",
        "Char ID",
        "Name",
        "Job Class",
        "Base Lv",
        "Job Lv",
        "ATK",
        "DEF",
    ]
    char_widths = [12, 16, 14, 13, 7, 6, 8, 7]
    char_rows = [
        [
            c["account_id"],
            c["character_id"],
            c["character_name"],
            c["job_class"],
            c["base_level"],
            c["job_level"],
            f"{c['atk']:.1f}",
            f"{c['def_attr']:.1f}",
        ]
        for c in characters
    ]
    print_table(
        "=== CHARACTER PROFILES OVERVIEW ===", char_headers, char_rows, char_widths
    )

    rarities = analytics.get_rarity_breakdown()
    rarity_headers = ["Rarity Category", "Drop Events", "Total Volume"]
    rarity_widths = [18, 12, 14]
    rarity_rows = [
        [r["rarity"], r["total_drop_events"], r["total_quantity"] or 0]
        for r in rarities
    ]
    print_table(
        "=== DROP BREAKDOWN BY RARITY ===", rarity_headers, rarity_rows, rarity_widths
    )

    top_items = analytics.get_top_items(limit=10)
    top_headers = ["Item Name", "Rarity", "Drop Count", "Total Harvested"]
    top_widths = [24, 12, 10, 15]
    top_rows = [
        [t["item_name"], t["rarity"], t["drop_occurrences"], t["total_quantity"] or 0]
        for t in top_items
    ]
    print_table(
        "=== TOP HARVESTED ITEMS LEADERBOARD ===", top_headers, top_rows, top_widths
    )

    monsters = analytics.get_monster_drop_summary()
    monster_headers = [
        "Monster Name",
        "Encounter Events",
        "Total Dropped",
        "Unique Items",
    ]
    monster_widths = [18, 16, 14, 12]
    monster_rows = [
        [
            m["monster_name"],
            m["drop_events"],
            m["total_items_dropped"] or 0,
            m["distinct_item_types"],
        ]
        for m in monsters
    ]
    print_table(
        "=== MONSTER YIELD SUMMARY ===", monster_headers, monster_rows, monster_widths
    )


def parse_args() -> argparse.Namespace:
    """Configures command-line options for running main.py."""
    parser = argparse.ArgumentParser(
        description="Ragnarok: The New World — Character & Drop Analytics System"
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Path to input JSON file containing accounts, characters, and drops.",
    )
    parser.add_argument(
        "--char-csv",
        type=Path,
        help="Path to input CSV file containing character metadata.",
    )
    parser.add_argument(
        "--drop-csv",
        type=Path,
        help="Path to input CSV file containing drop history logs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("Ragnarok_Analytics_Report.xlsx"),
        help="Output Excel filename.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_file = Path("ragnarok_analytics.db")

    if db_file.exists():
        db_file.unlink()  # Clean database reset

    print("=== Ragnarok: The New World — Character & Drop Analytics System ===")
    db_manager = DatabaseManager(db_file)
    print("[1/3] Initialized SQLite Database Schema and Indexes.")

    # Determine Data Loading Strategy
    if args.json and args.json.exists():
        print(f"[2/3] Importing data from JSON file: {args.json}...")
        import_json_data(db_manager, args.json)
    elif args.char_csv or args.drop_csv:
        print("[2/3] Importing data from CSV files...")
        import_csv_data(
            db_manager, char_csv_path=args.char_csv, drop_csv_path=args.drop_csv
        )
    else:
        print("[2/3] No input file specified. Seeding demo data...")
        seed_demo_data(db_manager)

    analytics = AnalyticsController(db_manager)

    print("\n[DISPLAYING CONSOLE ANALYTICS SUMMARY]")
    print_console_analytics(analytics, db_manager)

    print(f"\n[3/3] Exporting analytics workbook to {args.output}...")
    exporter = ExcelExporter(db_manager)

    try:
        saved_path = exporter.export_full_workbook(args.output)
        print(
            f"SUCCESS: Exported 3-tab workbook successfully to -> {saved_path.resolve()}"
        )
    except ExportError as err:
        print(f"ERROR: Export failed — {err}")


if __name__ == "__main__":
    main()
