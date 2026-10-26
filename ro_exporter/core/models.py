from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class Account:
    """Represents a game account holding multiple alt characters."""
    account_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.account_id or not self.account_id.strip():
            raise ValueError("Account ID cannot be empty or whitespace.")


@dataclass
class Character:
    """Represents an alt-character and its full statistical profile."""
    character_id: str
    account_id: str
    character_name: str
    job_class: str
    base_level: int
    job_level: int
    str_attr: int
    agi_attr: int
    vit_attr: int
    int_attr: int
    dex_attr: int
    luk_attr: int
    atk: float
    def_attr: float
    crit: float
    haste: float

    def __post_init__(self) -> None:
        if not self.character_id or not self.character_name:
            raise ValueError("Character ID and Name must be non-empty strings.")
        if self.base_level < 1 or self.job_level < 1:
            raise ValueError("Base level and Job level must be at least 1.")
        
        base_attrs = [self.str_attr, self.agi_attr, self.vit_attr, self.int_attr, self.dex_attr, self.luk_attr]
        if any(attr < 0 for attr in base_attrs):
            raise ValueError("Base stats (STR, AGI, VIT, INT, DEX, LUK) cannot be negative.")
        
        secondary_attrs = [self.atk, self.def_attr, self.crit, self.haste]
        if any(stat < 0.0 for stat in secondary_attrs):
            raise ValueError("Secondary stats (ATK, DEF, Crit, Haste) cannot be negative.")


@dataclass
class DropLog:
    """Represents a single item drop event logged by a character."""
    drop_id: Optional[int]
    character_id: str
    item_name: str
    rarity: str
    quantity: int
    monster_name: str
    dropped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Drop quantity must be greater than zero.")
        if not self.item_name or not self.monster_name or not self.rarity:
            raise ValueError("Item name, rarity, and monster name cannot be empty.")