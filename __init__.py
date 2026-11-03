"""GTInk - utilitas analisis dan kloning chip kartrid EAJet/GT1000.

Paket ini hanya memakai pustaka standar Python.
"""

from .card import (
    CARD_SIZE,
    BLOCK_SIZE,
    BLOCK_COUNT,
    DEFAULT_ACCESS,
    DEFAULT_GPB,
    DEFAULT_KEY,
    COUNTER_BLOCKS,
    COUNTER_OFFSET,
    PAYLOAD_SIZE,
    TAIL_SIZE,
    Card,
    CardError,
    load_card,
    load_cards,
)
from .replay import (
    AID,
    ATS,
    SETS,
    UID,
    ReplaySet,
    format_table as format_replay_table,
    get_set,
)

__all__ = [
    "CARD_SIZE",
    "BLOCK_SIZE",
    "BLOCK_COUNT",
    "DEFAULT_ACCESS",
    "DEFAULT_GPB",
    "DEFAULT_KEY",
    "COUNTER_BLOCKS",
    "COUNTER_OFFSET",
    "PAYLOAD_SIZE",
    "TAIL_SIZE",
    "Card",
    "CardError",
    "load_card",
    "load_cards",
    "AID",
    "ATS",
    "SETS",
    "UID",
    "ReplaySet",
    "format_replay_table",
    "get_set",
]

__version__ = "1.0.0"
