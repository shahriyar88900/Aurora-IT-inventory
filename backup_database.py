#!/usr/bin/env python3
"""Create a consistent SQLite backup while the inventory server is running."""

import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "inventory.db"
BACKUP_DIR = ROOT / "backups"

if not SOURCE.exists():
    raise SystemExit("Database not found. Start Aurora Plant IT Inventory at least once first.")

BACKUP_DIR.mkdir(exist_ok=True)
destination = BACKUP_DIR / f"inventory-{datetime.now():%Y-%m-%d_%H-%M-%S}.db"

with sqlite3.connect(SOURCE) as source, sqlite3.connect(destination) as backup:
    source.backup(backup)

print(f"Backup saved: {destination}")

