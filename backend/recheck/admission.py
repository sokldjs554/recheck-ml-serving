import asyncio
from contextlib import asynccontextmanager
import time


class Overloaded(Exception):
    pass


class DeadlineExceeded(Exception):
    pass


class Admission:
    """A bounded wait list; unlike a semaphore, admission itself has a cap."""
    def __init__(self, concurrency, queue):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.limit = concurrency + queue
        self.admitted = self.active = self.peak_active = self.peak_admitted = 0

    @asynccontextmanager
    async def slot(self, deadline):
        # No await between check and increment: atomic on this process's event loop.
        if self.admitted >= self.limit:
            raise Overloaded()
        self.admitted += 1
        self.peak_admitted = max(self.peak_admitted, self.admitted)
        acquired = False
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DeadlineExceeded()
            try:
                await asyncio.wait_for(self.semaphore.acquire(), remaining)
            except TimeoutError as exc:
                raise DeadlineExceeded() from exc
            acquired = True
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
            yield
        finally:
            if acquired:
                self.active -= 1
                self.semaphore.release()
            self.admitted -= 1
