"""Alert schemas per API_CONTRACT.md §6."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlertActionResponse(BaseModel):
    """Response returned when an alert is acknowledged or resolved."""

    id: str = Field(..., description="Alert identifier (e.g. alr_001)")
    state: str = Field(..., description="Current state: acknowledged | resolved")

