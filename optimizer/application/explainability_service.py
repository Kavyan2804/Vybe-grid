"""Explainability Service (Phase 2 Task 2.6 [STRETCH]).

Produces human-readable, one-line rationales for each hour's dispatch decision
based on physical constraints, battery reserve margins, solar surplus, and generator commitment.
"""

from typing import List
from optimizer.domain.entities import DispatchDecision, Site, Forecast


class ExplainabilityService:
    """Explains optimizer decisions in operator-facing plain language."""

    @staticmethod
    def explain_decision(
        decision: DispatchDecision,
        site: Site,
        forecast_solar_kw: float,
        is_start: bool = False,
        held_reserve: bool = False,
    ) -> str:
        """Produce a single-sentence rationale for a dispatch decision."""
        min_uptime = int(round(site.diesel_generator.min_uptime_h))

        if decision.diesel_on:
            if is_start:
                return (
                    f"Diesel started at {decision.diesel_kw:.1f} kW to serve load shortfall "
                    f"(min run-time: {min_uptime}h in effect)"
                )
            return (
                f"Diesel operating at {decision.diesel_kw:.1f} kW satisfying load & min run-time"
            )

        if held_reserve:
            return (
                f"Holding battery reserve (SoC {decision.soc_pct:.1f}%) "
                f"against forecast solar uncertainty"
            )

        if decision.battery_kw > 0.1:
            surplus = max(0.0, forecast_solar_kw - decision.solar_kw)
            return (
                f"Solar surplus ({surplus:.1f} kW) charging battery at {decision.battery_kw:.1f} kW"
            )

        if decision.battery_kw < -0.1:
            discharge_kw = abs(decision.battery_kw)
            return (
                f"Battery discharging {discharge_kw:.1f} kW to cover load and avoid diesel start"
            )

        if decision.solar_kw > 0.1:
            return f"Load served directly by solar generation ({decision.solar_kw:.1f} kW)"

        return "System in balance: solar, battery, and diesel idle"

    @classmethod
    def attach_explanations(
        cls,
        decisions: List[DispatchDecision],
        site: Site,
        forecast: Forecast,
    ) -> List[DispatchDecision]:
        """Attach plain-language reason to each decision in a series."""
        explained = []
        prev_diesel_on = False

        for hour, dec in enumerate(decisions):
            solar_fc = forecast.solar_kw[hour] if hour < len(forecast.solar_kw) else 0.0
            is_start = dec.diesel_on and not prev_diesel_on
            prev_diesel_on = dec.diesel_on

            reason = dec.reason or cls.explain_decision(
                decision=dec,
                site=site,
                forecast_solar_kw=solar_fc,
                is_start=is_start,
            )

            explained.append(
                DispatchDecision(
                    hour=dec.hour,
                    solar_kw=dec.solar_kw,
                    battery_kw=dec.battery_kw,
                    diesel_kw=dec.diesel_kw,
                    load_kw=dec.load_kw,
                    diesel_on=dec.diesel_on,
                    soc_pct=dec.soc_pct,
                    badges=list(dec.badges),
                    reason=reason,
                )
            )

        return explained
