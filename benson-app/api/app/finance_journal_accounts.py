from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from .finance_schema import ledger_accounts


DEFAULT_ACCOUNTS = {
    "1000": ("Cash", "asset"),
    "1100": ("Accounts receivable", "asset"),
    "1150": ("Retainage receivable", "asset"),
    "1180": ("Disputed funds", "asset"),
    "2000": ("Customer deposits", "liability"),
    "2100": ("Sales tax payable", "liability"),
    "4000": ("Construction revenue", "revenue"),
    "4050": ("Credits and write-offs", "revenue"),
    "6100": ("Payment processing fees", "expense"),
    "6200": ("Refunds", "expense"),
}


def ensure_default_accounts(db: Connection) -> None:
    existing = set(db.execute(select(ledger_accounts.c.code)).scalars())
    missing = [
        {"code": code, "name": name, "account_type": kind, "active": 1}
        for code, (name, kind) in DEFAULT_ACCOUNTS.items()
        if code not in existing
    ]
    if missing:
        db.execute(insert(ledger_accounts), missing)
