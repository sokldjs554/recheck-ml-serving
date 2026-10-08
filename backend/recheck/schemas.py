from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: int = Field(default=150000, ge=1, le=100000000)
    recipient: str = Field(default="demo-recipient", min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=128)
    delay_ms: int = Field(default=0, ge=0, le=2000)
    fault: Literal["none", "timeout", "unavailable"] = "none"
    protected: bool = True


class MutationRequest(BaseModel):
    kind: Literal["feature", "policy", "model"]


class InferenceRequest(BaseModel):
    features: list[float] = Field(min_length=4, max_length=4)
    model_version: str = Field(max_length=32)
    delay_ms: int = Field(default=0, ge=0, le=2000)
    fault: Literal["none", "timeout", "unavailable"] = "none"
    deadline_ms: float = Field(default=300, gt=0, le=2000)
