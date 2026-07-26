import asyncio
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    checks: dict[str, str]


async def check_readiness(engine: AsyncEngine, settings: Settings) -> ReadinessResult:
    database, redis = await asyncio.gather(
        _database_ready(engine, settings.readiness_timeout_seconds),
        _redis_ready(settings.redis_url, settings.readiness_timeout_seconds),
    )
    checks = {"database": database, "redis": redis}
    return ReadinessResult(ready=all(value == "ok" for value in checks.values()), checks=checks)


async def _database_ready(engine: AsyncEngine, timeout: float) -> str:
    async def probe() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(probe(), timeout=timeout)
    except Exception:
        return "unavailable"
    return "ok"


async def _redis_ready(url: str, timeout: float) -> str:
    client = Redis.from_url(url, socket_connect_timeout=timeout, socket_timeout=timeout)
    try:
        await asyncio.wait_for(client.ping(), timeout=timeout)
    except Exception:
        return "unavailable"
    finally:
        await client.aclose()
    return "ok"
