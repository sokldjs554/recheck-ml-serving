"""Bounded CPU execution; admission remains owned by the background inference task."""
import asyncio
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import multiprocessing

class ExecutionUnavailable(Exception):
    """The CPU pool cannot accept work and requires a supervisor restart."""


_MODELS = {}


def _initialize(models):
    global _MODELS
    _MODELS = models


def _predict(version, features):
    base_version = 'risk-v1' if int(version.split('v')[1]) % 2 else 'risk-v2'
    return _MODELS[base_version].score(features)


class Execution:
    def __init__(self, settings, models):
        self.settings = settings
        self.models = models
        self.pool = None
        self.submitted = 0
        self._failed = False

    @property
    def unavailable(self):
        # CPython exposes no public idle-pool health API. Its manager sets this
        # flag on unexpected child exit, before another request is submitted.
        # Submission/result exception handling below is the public-API fallback.
        return self._failed or bool(getattr(self.pool, "_broken", False))

    async def start(self):
        if self.settings.execution_mode == 'process':
            self.pool = ProcessPoolExecutor(max_workers=self.settings.worker_concurrency,
                mp_context=multiprocessing.get_context('spawn'),
                initializer=_initialize, initargs=(self.models,))
            # Readiness waits for process initialization and a real prediction.
            await asyncio.gather(*(asyncio.get_running_loop().run_in_executor(
                self.pool, _predict, 'risk-v1', [0.1, 0, 0, 0.1])
                for _ in range(self.settings.worker_concurrency)))

    async def score(self, model, features):
        if self.unavailable:
            raise ExecutionUnavailable()
        self.submitted += 1
        if self.settings.execution_mode == 'inline':
            return model.score(features)
        if self.pool is None:
            raise RuntimeError('process execution requires application lifespan startup')
        try:
            return await asyncio.get_running_loop().run_in_executor(self.pool, _predict, model.model_version, features)
        except BrokenProcessPool as exc:
            self._failed = True
            raise ExecutionUnavailable() from exc

    async def close(self):
        if self.pool is not None:
            await asyncio.to_thread(self.pool.shutdown, wait=True, cancel_futures=True)
