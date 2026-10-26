from typing import Any, Dict, List
from database import DatabaseManager


class AnalyticsController:
    """Calculates aggregate statistics and analytics reports for drop distributions."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    def get_rarity_breakdown(self) -> List[Dict[str, Any]]:
        sql = """
            SELECT 
                rarity,
                COUNT(drop_id) AS total_drop_events,
                SUM(quantity) AS total_quantity
            FROM drop_logs
            GROUP BY rarity
            ORDER BY total_quantity DESC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    def get_top_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        sql = """
            SELECT 
                item_name,
                rarity,
                COUNT(drop_id) AS drop_occurrences,
                SUM(quantity) AS total_quantity
            FROM drop_logs
            GROUP BY item_name, rarity
            ORDER BY total_quantity DESC
            LIMIT ?;
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute(sql, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_monster_drop_summary(self) -> List[Dict[str, Any]]:
        sql = """
            SELECT 
                monster_name,
                COUNT(drop_id) AS drop_events,
                SUM(quantity) AS total_items_dropped,
                COUNT(DISTINCT item_name) AS distinct_item_types
            FROM drop_logs
            GROUP BY monster_name
            ORDER BY total_items_dropped DESC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]