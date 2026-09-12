"""Tests for the generated Phase 1 OpenAPI documentation."""

from __future__ import annotations

from src.main import app


def test_openapi_documents_phase1_mock_backend() -> None:
    document = app.openapi()

    assert document["info"]["title"] == "Vybe-grid Phase 1 Backend API"
    assert document["info"]["version"] == "0.1.0-phase1"
    assert "development-only" in document["info"]["description"]
    assert {tag["name"] for tag in document["tags"]} == {
        "sites",
        "plans",
        "alerts",
        "health",
    }

    create_plan = document["paths"]["/api/plans/mock"]["post"]
    assert create_plan["summary"] == "Create a deterministic mock plan"
    assert "not optimizer output" in create_plan["description"]
    assert "201" in create_plan["responses"]
    assert "422" in create_plan["responses"]

    create_site = document["paths"]["/api/sites"]["post"]
    assert "requestBody" in create_site
    assert "examples" in create_site["requestBody"]["content"]["application/json"]

    alert_list = document["paths"]["/api/alerts"]["get"]
    assert "limit" in alert_list["parameters"][2]["name"] or "limit" in {
        parameter["name"] for parameter in alert_list["parameters"]
    }

    error_schema = document["components"]["schemas"]["ErrorResponse"]
    assert {"error", "message", "field_errors", "path", "timestamp"} <= set(
        error_schema["properties"]
    )
    assert "example" in error_schema
