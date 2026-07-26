import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncRunner:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def run(self, coroutine: Coroutine[Any, Any, T]) -> T:
        loop = self._get_loop()
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._run_loop,
                    name="benson-worker-async-loop",
                    daemon=True,
                )
                self._thread.start()
            return self._loop

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()


async_runner = AsyncRunner()
