"""‌⁠‍SQLite auto-migrator.

On startup, compares existing SQLite schema against SQLAlchemy models
and adds any missing columns via ALTER TABLE ADD COLUMN.

This handles the common upgrade case (new columns in new versions)
without requiring full Alembic for SQLite users.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def sqlite_auto_migrate(engine: AsyncEngine, base) -> int:
    """‌⁠‍Compare SQLAlchemy models against SQLite schema and add missing columns.

    Args:
        engine: The async SQLAlchemy engine (must be SQLite)
        base: The declarative Base class containing all model metadata

    Returns:
        Number of columns added
    """
    columns_added = 0

    async with engine.begin() as conn:
        # Get existing table names
        existing_tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())

        for table in base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # New table — create_all will handle it

            # Get existing columns for this table
            existing_cols = await conn.run_sync(
                lambda sync_conn, tn=table.name: {col["name"] for col in inspect(sync_conn).get_columns(tn)}
            )

            # Check each model column
            for col in table.columns:
                if col.name in existing_cols:
                    continue

                # Build ALTER TABLE statement
                col_type = col.type.compile(engine.dialect)
                nullable = "NULL" if col.nullable else "NOT NULL"
                default = ""
                if col.server_default is not None:
                    raw = col.server_default.arg
                    if isinstance(raw, str):
                        # Ensure string defaults are properly quoted for SQLite
                        if not raw.startswith("'"):
                            raw = "'" + raw.replace("'", "''") + "'"
                        default = f" DEFAULT {raw}"
                    else:
                        # Non-string server_default (e.g. func.now() /
                        # CURRENT_TIMESTAMP / any expression). SQLite forbids a
                        # function or expression as the DEFAULT in ALTER TABLE
                        # ADD COLUMN, so the ALTER would fail silently and leave
                        # the column missing (the original bug behind the
                        # oe_notification_digest_queue.updated_at drift, which
                        # 500s every ORM read of that table). Compile it; if it
                        # is a literal constant keep it, otherwise substitute a
                        # constant so the column actually gets added.
                        try:
                            compiled = str(
                                raw.compile(
                                    dialect=engine.dialect,
                                    compile_kwargs={"literal_binds": True},
                                )
                            )
                        except Exception:  # noqa: BLE001
                            compiled = ""
                        low = compiled.lower()
                        if not compiled or "(" in compiled or "now" in low or "current_" in low:
                            if col.nullable:
                                default = " DEFAULT NULL"
                            else:
                                # Backfill existing rows with the migration time
                                # (a constant literal SQLite accepts). New rows
                                # get the real default via the app on write.
                                stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                                default = f" DEFAULT '{stamp}'"
                        else:
                            default = f" DEFAULT {compiled}"
                elif col.nullable:
                    default = " DEFAULT NULL"

                sql = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type} {nullable}{default}'

                try:
                    await conn.execute(text(sql))
                    columns_added += 1
                    logger.info(
                        "SQLite migration: added column %s.%s (%s)",
                        table.name,
                        col.name,
                        col_type,
                    )
                except Exception as exc:
                    logger.warning(
                        "SQLite migration: failed to add %s.%s: %s",
                        table.name,
                        col.name,
                        exc,
                    )

    if columns_added > 0:
        logger.info("SQLite auto-migration complete: %d columns added", columns_added)

    return columns_added
