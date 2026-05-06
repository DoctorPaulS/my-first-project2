from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScanResult:
    ticker: str
    score: float
    signal: str
    reasoning: str
    indicator_detail: dict
    earnings_warning: bool
    sentiment_flag: bool
    scanned_at: Optional[datetime] = None
    id: Optional[str] = None


@dataclass
class WatchlistItem:
    ticker: str
    added_at: Optional[datetime] = None
    notes: Optional[str] = None
    id: Optional[str] = None


@dataclass
class Alert:
    ticker: str
    previous_signal: str
    new_signal: str
    read: bool = False
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    id: Optional[str] = None
