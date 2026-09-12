"""Typed alert schemas shared by Phase 1 APIs and Phase 3 rules."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.common import ProvenanceBadge


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertType(str, Enum):
    """Alert conditions defined by the Phase 3 contract."""

    LOW_SOC_RESERVE = "LOW_SOC_RESERVE"
    DIESEL_REQUIRED_SOON = "DIESEL_REQUIRED_SOON"
    CRITICAL_LOAD_AT_RISK = "CRITICAL_LOAD_AT_RISK"
    SOLVER_FALLBACK_ACTIVE = "SOLVER_FALLBACK_ACTIVE"
    FORECAST_STALE = "FORECAST_STALE"
    BASELINE_DIVERGENCE = "BASELINE_DIVERGENCE"


class AlertState(str, Enum):
    """Phase 3 alert lifecycle state."""

    CREATED = "created"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str = Field(..., min_length=1, max_length=64, examples=["demo-site"])
    severity: AlertSeverity = Field(..., examples=["warning"])
    title: str = Field(..., min_length=1, max_length=160, examples=["Low battery reserve"])
    message: str = Field(
        ..., min_length=1, max_length=1000, examples=["Battery reserve is below target."]
    )


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., examples=["alr_001"])
    site_id: str = Field(..., examples=["demo-site"])
    type: AlertType = AlertType.LOW_SOC_RESERVE
    subject: str | None = Field(None, min_length=1, max_length=160)
    state: AlertState = AlertState.CREATED
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE
    title: str
    message: str
    created_at: datetime
    raised_at: datetime | None = None
    received_at: datetime | None = None
    provenance: list[ProvenanceBadge] = Field(default_factory=lambda: [ProvenanceBadge.SIMULATED])
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    @field_validator(
        "created_at",
        "raised_at",
        "received_at",
        "acknowledged_at",
        "resolved_at",
    )
    @classmethod
    def require_timezone_aware_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("alert timestamps must include an explicit timezone offset")
        return value

    def transition_to(self, target: AlertState) -> Alert:
        """Return a copy in a valid lifecycle state, without mutating this model."""

        valid_targets = {
            AlertState.CREATED: {AlertState.ACKNOWLEDGED, AlertState.RESOLVED},
            AlertState.ACKNOWLEDGED: {AlertState.RESOLVED},
            AlertState.RESOLVED: set(),
        }
        if target not in valid_targets[self.state]:
            raise ValueError(f"invalid alert transition: {self.state.value} -> {target.value}")
        return self.model_copy(update={"state": target})


class AlertListResponse(BaseModel):
    total: int = Field(..., ge=0, description="Total matching alerts before pagination")
    items: list[Alert] = Field(..., description="Paginated matching alerts")


class AlertActionResponse(BaseModel):
    """Response returned after an alert state transition."""

    id: str = Field(..., description="Alert identifier")
    state: AlertStatus = Field(..., description="New alert status")
