from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./recheck.db"
    model_service_url: str = "http://127.0.0.1:8001"
    deadline_ms: int = 300
    receipt_ttl_ms: int = 15000
    feature_ttl_ms: int = 60000
    session_ttl_seconds: int = 3600
    gateway_concurrency: int = 8
    gateway_queue: int = 16
    worker_concurrency: int = 2
    worker_queue: int = 8
    workload: str = "lightweight"
    execution_mode: str = "inline"
    max_sessions: int = 1000
    max_receipts: int = 100
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    def __post_init__(self):
        if self.workload not in ("lightweight", "cpu-ensemble"):
            raise ValueError("unknown workload")
        if self.execution_mode not in ("inline", "process"):
            raise ValueError("unknown execution mode")
        for name in ("deadline_ms", "receipt_ttl_ms", "feature_ttl_ms", "session_ttl_seconds",
                     "gateway_concurrency", "worker_concurrency", "max_sessions", "max_receipts"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.gateway_queue < 0 or self.worker_queue < 0:
            raise ValueError("queue sizes must be nonnegative")
        if self.deadline_ms > 2000:
            raise ValueError("deadline_ms is capped at 2000")

    @classmethod
    def from_env(cls):
        values = {}
        for name, field in cls.__dataclass_fields__.items():
            key = {"database_url": "DATABASE_URL", "model_service_url": "MODEL_SERVICE_URL"}.get(name, "RECHECK_" + name.upper())
            value = os.getenv(key)
            if value is not None:
                values[name] = tuple(x.strip() for x in value.split(",") if x.strip()) if name == "cors_origins" else int(value) if isinstance(field.default, int) else value
        return cls(**values)
