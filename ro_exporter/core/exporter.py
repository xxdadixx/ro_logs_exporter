from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from analytics import AnalyticsController
from database import DatabaseManager


class ExportError(Exception):
    """Custom exception raised when Excel export operations fail."""

    pass


class ExcelExporter:
    """High-reliability engine for generating formatted, type-safe multi-tab Excel workbooks."""

    HEADER_FILL = PatternFill(
        start_color="1F4E78", end_color="1F4E78", fill_type="solid"
    )
    HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    SUBHEADER_FILL = PatternFill(
        start_color="2F5597", end_color="2F5597", fill_type="solid"
    )
    TOTAL_FILL = PatternFill(
        start_color="F2F2F2", end_color="F2F2F2", fill_type="solid"
    )
    BOLD_FONT = Font(name="Calibri", size=11, bold=True)
    DATA_FONT = Font(name="Calibri", size=10)
    BORDER_THIN = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager
        self.analytics = AnalyticsController(db_manager)

    def export_full_workbook(
        self,
        output_path: str | Path,
        filter_char_name: Optional[str] = None,
        filter_rarity: Optional[str] = None,
        filter_start_date: Optional[str] = None,
        filter_end_date: Optional[str] = None,
    ) -> Path:
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()
        # Remove default sheet
        default_sheet = wb.active
        if default_sheet is not None:
            wb.remove(default_sheet)

        # Tab 1: Characters Summary
        ws1 = wb.create_sheet(title="Characters Summary")
        self._build_characters_tab(ws1)

        # Tab 2: Drop History Log
        ws2 = wb.create_sheet(title="Drop History Log")
        self._build_drop_history_tab(
            ws2, filter_char_name, filter_rarity, filter_start_date, filter_end_date
        )

        # Tab 3: Analytics Dashboard
        ws3 = wb.create_sheet(title="Analytics Dashboard")
        self._build_analytics_tab(ws3)

        try:
            wb.save(target_path)
            return target_path
        except PermissionError as e:
            raise ExportError(
                f"Failed to write workbook: File '{target_path.name}' is currently locked. "
                "Please close Microsoft Excel or any application accessing the file and retry."
            ) from e
        except Exception as e:
            raise ExportError(f"Unexpected error saving Excel workbook: {e}") from e

    def _build_characters_tab(self, ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
        headers = [
            "Account ID",
            "Character ID",
            "Character Name",
            "Job Class",
            "Base Level",
            "Job Level",
            "STR",
            "AGI",
            "VIT",
            "INT",
            "DEX",
            "LUK",
            "ATK",
            "DEF",
            "Crit",
            "Haste",
        ]
        ws.append(headers)
        self._format_header_row(ws, len(headers))

        characters = self.db.get_all_characters_with_account()
        for c in characters:
            row = [
                str(c["account_id"]),
                str(c["character_id"]),
                str(c["character_name"]),
                str(c["job_class"]),
                int(c["base_level"]),
                int(c["job_level"]),
                int(c["str_attr"]),
                int(c["agi_attr"]),
                int(c["vit_attr"]),
                int(c["int_attr"]),
                int(c["dex_attr"]),
                int(c["luk_attr"]),
                float(c["atk"]),
                float(c["def_attr"]),
                float(c["crit"]),
                float(c["haste"]),
            ]
            ws.append(row)

        self._apply_data_formatting(ws, start_row=2, max_col=len(headers))
        ws.auto_filter.ref = ws.dimensions
        self._autofit_columns(ws)

    def _build_drop_history_tab(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        char_name: Optional[str],
        rarity: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> None:
        headers = [
            "Drop ID",
            "Account ID",
            "Character ID",
            "Character Name",
            "Item Name",
            "Item Rarity",
            "Quantity",
            "Source Monster",
            "Dropped At (UTC)",
        ]
        ws.append(headers)
        self._format_header_row(ws, len(headers))

        drops = self.db.get_filtered_drops(char_name, rarity, start_date, end_date)
        row_idx = 2
        for d in drops:
            # Strip tzinfo so openpyxl writes native Excel datetime cells without throwing exceptions
            dropped_at_val = self._to_naive_datetime(d["dropped_at"])

            row = [
                int(d["drop_id"]),
                str(d["account_id"]),
                str(d["character_id"]),
                str(d["character_name"]),
                str(d["item_name"]),
                str(d["rarity"]),
                int(d["quantity"]),
                str(d["monster_name"]),
                dropped_at_val,
            ]
            ws.append(row)
            row_idx += 1

        self._apply_data_formatting(ws, start_row=2, max_col=len(headers))

        # Add Summary Total Row using native Excel formula
        if row_idx > 2:
            total_row_idx = row_idx
            ws.cell(row=total_row_idx, column=1, value="Total Items Harvested").font = (
                self.BOLD_FONT
            )
            ws.cell(
                row=total_row_idx, column=7, value=f"=SUM(G2:G{total_row_idx - 1})"
            ).font = self.BOLD_FONT

            for c in range(1, len(headers) + 1):
                cell = ws.cell(row=total_row_idx, column=c)
                cell.fill = self.TOTAL_FILL
                cell.border = self.BORDER_THIN

        ws.auto_filter.ref = f"A1:I{max(2, row_idx - 1)}"
        self._autofit_columns(ws)

    def _build_analytics_tab(self, ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
        # Section 1: Drop Breakdown by Rarity
        ws.append(["Rarity Aggregate Statistics"])
        ws.cell(row=1, column=1).font = Font(
            name="Calibri", size=13, bold=True, color="1F4E78"
        )

        headers_rarity = ["Rarity Category", "Total Drop Events", "Total Item Volume"]
        ws.append(headers_rarity)
        self._format_row_at_index(
            ws, 2, len(headers_rarity), self.HEADER_FILL, self.HEADER_FONT
        )

        rarities = self.analytics.get_rarity_breakdown()
        curr_row = 3
        for r in rarities:
            ws.append(
                [
                    str(r["rarity"]),
                    int(r["total_drop_events"]),
                    int(r["total_quantity"] or 0),
                ]
            )
            curr_row += 1

        # Section 2: Top 10 Drops
        curr_row += 2
        ws.cell(row=curr_row, column=1, value="Top 10 Harvested Items").font = Font(
            name="Calibri", size=13, bold=True, color="1F4E78"
        )
        curr_row += 1

        headers_top = ["Item Name", "Rarity", "Drop Occurrences", "Total Quantity"]
        ws.cell(row=curr_row, column=1)  # trigger alignment
        for col_idx, h in enumerate(headers_top, 1):
            cell = ws.cell(row=curr_row, column=col_idx, value=h)
            cell.fill = self.SUBHEADER_FILL
            cell.font = self.HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center")
        curr_row += 1

        top_items = self.analytics.get_top_items(limit=10)
        for item in top_items:
            ws.append(
                [
                    str(item["item_name"]),
                    str(item["rarity"]),
                    int(item["drop_occurrences"]),
                    int(item["total_quantity"] or 0),
                ]
            )
            curr_row += 1

        # Section 3: Monster Yield Analytics
        curr_row += 2
        ws.cell(row=curr_row, column=1, value="Monster Yield Breakdown").font = Font(
            name="Calibri", size=13, bold=True, color="1F4E78"
        )
        curr_row += 1

        headers_monster = [
            "Monster Name",
            "Encounter Drop Events",
            "Total Items Dropped",
            "Unique Item Types",
        ]
        for col_idx, h in enumerate(headers_monster, 1):
            cell = ws.cell(row=curr_row, column=col_idx, value=h)
            cell.fill = self.HEADER_FILL
            cell.font = self.HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center")
        curr_row += 1

        monsters = self.analytics.get_monster_drop_summary()
        for m in monsters:
            ws.append(
                [
                    str(m["monster_name"]),
                    int(m["drop_events"]),
                    int(m["total_items_dropped"] or 0),
                    int(m["distinct_item_types"]),
                ]
            )
            curr_row += 1

        self._autofit_columns(ws)

    def _format_header_row(
        self, ws: openpyxl.worksheet.worksheet.Worksheet, max_col: int
    ) -> None:
        self._format_row_at_index(ws, 1, max_col, self.HEADER_FILL, self.HEADER_FONT)

    def _format_row_at_index(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        row_idx: int,
        max_col: int,
        fill: PatternFill,
        font: Font,
    ) -> None:
        for col in range(1, max_col + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.fill = fill
            cell.font = font
            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )

    def _apply_data_formatting(
        self, ws: openpyxl.worksheet.worksheet.Worksheet, start_row: int, max_col: int
    ) -> None:
        for row in ws.iter_rows(min_row=start_row, max_col=max_col, max_row=ws.max_row):
            for cell in row:
                cell.font = self.DATA_FONT
                cell.border = self.BORDER_THIN
                if isinstance(cell.value, (int, float)):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif isinstance(cell.value, datetime):
                    cell.number_format = "YYYY-MM-DD HH:MM:SS"
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

    def _autofit_columns(self, ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if "\n" in val:
                    lines = val.split("\n")
                    max_len = max(max_len, max(len(line) for line in lines))
                else:
                    max_len = max(max_len, len(val))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # Insert this helper method inside the ExcelExporter class in exporter.py

    @staticmethod
    def _to_naive_datetime(val: Any) -> Any:
        """Converts ISO date strings or tz-aware datetimes to naive datetimes for openpyxl compatibility."""
        if isinstance(val, datetime):
            return val.replace(tzinfo=None)
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val)
                return dt.replace(tzinfo=None)
            except ValueError:
                return val
        return val
