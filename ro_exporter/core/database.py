import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from models import Account, Character, DropLog


class DatabaseError(Exception):
    """Custom exception raised for critical database operational failures."""
    pass


class DatabaseManager:
    """Handles SQLite connection pooling, transactional integrity, and CRUD operations."""

    def __init__(self, db_path: str | Path = "ragnarok_analytics.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides a transactional database connection context."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as err:
            conn.rollback()
            raise DatabaseError(f"Database execution error: {err}") from err
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initializes database schema and indexes atomically."""
        schema = """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS characters (
            character_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            character_name TEXT NOT NULL,
            job_class TEXT NOT NULL,
            base_level INTEGER NOT NULL CHECK(base_level >= 1),
            job_level INTEGER NOT NULL CHECK(job_level >= 1),
            str_attr INTEGER NOT NULL DEFAULT 0 CHECK(str_attr >= 0),
            agi_attr INTEGER NOT NULL DEFAULT 0 CHECK(agi_attr >= 0),
            vit_attr INTEGER NOT NULL DEFAULT 0 CHECK(vit_attr >= 0),
            int_attr INTEGER NOT NULL DEFAULT 0 CHECK(int_attr >= 0),
            dex_attr INTEGER NOT NULL DEFAULT 0 CHECK(dex_attr >= 0),
            luk_attr INTEGER NOT NULL DEFAULT 0 CHECK(luk_attr >= 0),
            atk REAL NOT NULL DEFAULT 0.0 CHECK(atk >= 0),
            def_attr REAL NOT NULL DEFAULT 0.0 CHECK(def_attr >= 0),
            crit REAL NOT NULL DEFAULT 0.0 CHECK(crit >= 0),
            haste REAL NOT NULL DEFAULT 0.0 CHECK(haste >= 0),
            FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS drop_logs (
            drop_id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            rarity TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            monster_name TEXT NOT NULL,
            dropped_at TEXT NOT NULL,
            FOREIGN KEY (character_id) REFERENCES characters(character_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_characters_account_id ON characters(account_id);
        CREATE INDEX IF NOT EXISTS idx_drop_logs_character_id ON drop_logs(character_id);
        CREATE INDEX IF NOT EXISTS idx_drop_logs_dropped_at ON drop_logs(dropped_at);
        CREATE INDEX IF NOT EXISTS idx_drop_logs_rarity ON drop_logs(rarity);
        CREATE INDEX IF NOT EXISTS idx_drop_logs_item_name ON drop_logs(item_name);
        """
        with self.get_connection() as conn:
            conn.executescript(schema)

    def create_account(self, account: Account) -> None:
        """Inserts an account if it does not already exist."""
        sql = "INSERT OR IGNORE INTO accounts (account_id, created_at) VALUES (?, ?)"
        with self.get_connection() as conn:
            conn.execute(sql, (account.account_id, account.created_at.isoformat()))

    def upsert_character(self, character: Character) -> None:
        sql = """
            INSERT INTO characters (
                character_id, account_id, character_name, job_class, base_level, job_level,
                str_attr, agi_attr, vit_attr, int_attr, dex_attr, luk_attr,
                atk, def_attr, crit, haste
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(character_id) DO UPDATE SET
                account_id = excluded.account_id,
                character_name = excluded.character_name,
                job_class = excluded.job_class,
                base_level = excluded.base_level,
                job_level = excluded.job_level,
                str_attr = excluded.str_attr,
                agi_attr = excluded.agi_attr,
                vit_attr = excluded.vit_attr,
                int_attr = excluded.int_attr,
                dex_attr = excluded.dex_attr,
                luk_attr = excluded.luk_attr,
                atk = excluded.atk,
                def_attr = excluded.def_attr,
                crit = excluded.crit,
                haste = excluded.haste;
        """
        params = (
            character.character_id, character.account_id, character.character_name,
            character.job_class, character.base_level, character.job_level,
            character.str_attr, character.agi_attr, character.vit_attr,
            character.int_attr, character.dex_attr, character.luk_attr,
            character.atk, character.def_attr, character.crit, character.haste
        )
        with self.get_connection() as conn:
            conn.execute(sql, params)

    def add_drop_log(self, drop: DropLog) -> int:
        sql = """
            INSERT INTO drop_logs (character_id, item_name, rarity, quantity, monster_name, dropped_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            drop.character_id, drop.item_name, drop.rarity,
            drop.quantity, drop.monster_name, drop.dropped_at.isoformat()
        )
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid or 0

    def get_all_characters_with_account(self) -> List[Dict[str, Any]]:
        sql = """
            SELECT c.*, a.account_id
            FROM characters c
            JOIN accounts a ON c.account_id = a.account_id
            ORDER BY c.account_id, c.character_name;
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    def get_filtered_drops(
        self,
        character_name: Optional[str] = None,
        rarity: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT d.drop_id, c.account_id, d.character_id, c.character_name,
                   d.item_name, d.rarity, d.quantity, d.monster_name, d.dropped_at
            FROM drop_logs d
            JOIN characters c ON d.character_id = c.character_id
            WHERE 1=1
        """
        params: List[Any] = []
        if character_name:
            sql += " AND c.character_name LIKE ?"
            params.append(f"%{character_name}%")
        if rarity:
            sql += " AND d.rarity = ?"
            params.append(rarity)
        if start_date:
            sql += " AND d.dropped_at >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND d.dropped_at <= ?"
            params.append(end_date)

        sql += " ORDER BY d.dropped_at DESC;"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]