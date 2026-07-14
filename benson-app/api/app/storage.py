import json
import sqlite3
from pathlib import Path

from .domain import LeadIntake, LeadReceipt


class OperationsStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, accepted_at TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, event TEXT NOT NULL, occurred_at TEXT NOT NULL, payload TEXT NOT NULL)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def save_lead(self, receipt: LeadReceipt, lead: LeadIntake) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO leads (id, accepted_at, payload) VALUES (?, ?, ?)",
                (str(receipt.lead_id), receipt.accepted_at.isoformat(), lead.model_dump_json()),
            )
            db.execute(
                "INSERT INTO audit (event, occurred_at, payload) VALUES (?, ?, ?)",
                ("lead.accepted", receipt.accepted_at.isoformat(), json.dumps({"lead_id": str(receipt.lead_id)})),
            )

    def lead_count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM leads").fetchone()[0])
