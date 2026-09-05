import asyncio

import pytest
from app.workers.async_runner import AsyncRunner
from app.workers.processor import retry_delay_seconds
from app.workers.registry import HandlerRegistry, record_domain_event


def test_retry_delay_is_exponential_and_capped() -> None:
    assert retry_delay_seconds(1, 10, 100) == 10
    assert retry_delay_seconds(2, 10, 100) == 20
    assert retry_delay_seconds(8, 10, 100) == 100


def test_handler_registry_rejects_duplicates_and_unknown_events() -> None:
    registry = HandlerRegistry()
    registry.register("Example", "example-handler", record_domain_event)
    registry.register("Example", "second-handler", record_domain_event)

    assert [handler.name for handler in registry.resolve("Example")] == [
        "example-handler",
        "second-handler",
    ]
    with pytest.raises(ValueError, match="already registered"):
        registry.register("Example", "example-handler", record_domain_event)
    with pytest.raises(LookupError, match="No handler"):
        registry.resolve("Unknown")


def test_async_runner_reuses_one_background_loop() -> None:
    runner = AsyncRunner()

    async def loop_identity() -> int:
        return id(asyncio.get_running_loop())

    assert runner.run(loop_identity()) == runner.run(loop_identity())
