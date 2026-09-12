"""Typed alert schemas for the Phase 1 API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str = Field(..., min_length=1, max_length=64, examples=["demo-site"])
    severity: AlertSeverity = Field(..., examples=["warning"])
    title: str = Field(..., min_length=1, max_length=160, examples=["Low battery reserve"])
    message: str = Field(..., min_length=1, max_length=1000, examples=["Battery reserve is below target."])


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., examples=["alr_001"])
    site_id: str = Field(..., examples=["demo-site"])
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE
    title: str
    message: str
    created_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


class AlertListResponse(BaseModel):
    total: int = Field(..., ge=0, description="Total matching alerts before pagination")
    items: list[Alert] = Field(..., description="Paginated matching alerts")


class AlertActionResponse(BaseModel):
    """Response returned after an alert state transition."""

    id: str = Field(..., description="Alert identifier")
    state: AlertStatus = Field(..., description="New alert status")
