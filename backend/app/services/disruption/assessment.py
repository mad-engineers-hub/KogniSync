"""
backend/app/services/disruption/assessment.py

Deterministic Journey Impact Assessment Engine (Milestone M3.7).
Calculates per-segment delay, arrival time slip, transfer buffer reduction,
and connection risk without mutating canonical inventory or fabricating live measurements.
"""
from datetime import datetime, timezone, timedelta
from typing import Sequence
from app.services.disruption.matcher import (
    MatchedSegmentDisruption,
    RouteDisruptionMatcher,
    route_disruption_matcher,
)
from app.services.disruption.schemas import (
    ConnectionRiskLevel,
    DisruptedSegmentImpact,
    DisruptionEvent,
    DisruptionImpactLevel,
    DisruptionSeverity,
    JourneyDisruptionAssessment,
)
from app.services.journey.schemas import JourneySchema, JourneySegmentSchema, ProvenanceSourceType

SEVERITY_ORDER: dict[DisruptionSeverity, int] = {
    "critical": 4,
    "high": 3,
    "moderate": 2,
    "low": 1,
    "unknown": 0,
}

IMPACT_ORDER: dict[DisruptionImpactLevel, int] = {
    "critical": 4,
    "high": 3,
    "moderate": 2,
    "low": 1,
    "none": 0,
    "unknown": 0,
}


def parse_iso_datetime(iso_str: str) -> datetime | None:
    """Defensively parses ISO timestamp strings."""
    if not iso_str:
        return None
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        try:
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if ":" in iso_str and len(iso_str) <= 8:
                return datetime.fromisoformat(f"{today_str}T{iso_str}+00:00")
        except Exception:
            pass
        return None


def format_iso_datetime(dt: datetime) -> str:
    """Formats datetime as ISO 8601 string."""
    return dt.isoformat()


class JourneyImpactAssessor:
    """Pure, deterministic engine assessing disruption consequences across a journey."""

    def __init__(self, matcher: RouteDisruptionMatcher | None = None):
        self.matcher = matcher or route_disruption_matcher

    def assess_journey(
        self,
        journey: JourneySchema,
        events: Sequence[DisruptionEvent],
    ) -> JourneyDisruptionAssessment:
        """
        Evaluates active disruption events against all journey segments.
        Calculates delay, transfer erosion, and connection risks deterministically.
        """
        matched_by_segment = self.matcher.match_events_to_segments(
            events=events,
            segments=journey.segments,
        )

        segment_impacts: list[DisruptedSegmentImpact] = []
        all_matched_events: list[DisruptionEvent] = []
        seen_event_ids: set[str] = set()

        total_accumulated_delay_min = 0
        critical_risk_count = 0
        overall_max_impact: DisruptionImpactLevel = "none"
        highest_severity: DisruptionSeverity = "low"
        is_any_simulated = False
        is_any_live = False

        for idx, segment in enumerate(journey.segments):
            matches = matched_by_segment.get(segment.segment_id, [])
            next_segment: JourneySegmentSchema | None = (
                journey.segments[idx + 1] if idx + 1 < len(journey.segments) else None
            )

            impact = self._assess_segment(
                segment=segment,
                matches=matches,
                next_segment=next_segment,
                prior_cumulative_delay_min=total_accumulated_delay_min,
            )
            segment_impacts.append(impact)

            # Accumulate overall stats
            total_accumulated_delay_min += impact.estimated_delay_minutes

            if IMPACT_ORDER[impact.impact_level] > IMPACT_ORDER[overall_max_impact]:
                overall_max_impact = impact.impact_level

            if impact.subsequent_transfer_risk in ("critical", "missed_estimated"):
                critical_risk_count += 1

            for m in matches:
                if m.event.id not in seen_event_ids:
                    seen_event_ids.add(m.event.id)
                    all_matched_events.append(m.event)
                    if SEVERITY_ORDER[m.event.severity] > SEVERITY_ORDER[highest_severity]:
                        highest_severity = m.event.severity
                    if m.event.provenance == "simulated":
                        is_any_simulated = True
                    elif m.event.provenance == "provider_live":
                        is_any_live = True

        is_disrupted = len(all_matched_events) > 0 and overall_max_impact != "none"
        affected_count = sum(1 for imp in segment_impacts if imp.impact_level != "none")

        # Provenance attribution
        provenance: ProvenanceSourceType = (
            "simulated"
            if is_any_simulated
            else ("provider_live" if is_any_live else "deterministic_estimate")
        )

        # Build comprehensive summary narrative
        summary = self._build_assessment_summary(
            is_disrupted=is_disrupted,
            affected_count=affected_count,
            highest_severity=highest_severity,
            overall_max_impact=overall_max_impact,
            total_delay=total_accumulated_delay_min,
            critical_risk_count=critical_risk_count,
            events=all_matched_events,
            provenance=provenance,
        )

        has_aging = any(getattr(e, "data_freshness_status", None) == "aging" for e in all_matched_events)
        has_stale = any(getattr(e, "data_freshness_status", None) == "stale" for e in all_matched_events)

        if is_any_simulated:
            notice = "SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA"
        elif has_stale:
            notice = "STALE PROVIDER OBSERVATION — VERIFY BEFORE TRAVEL"
        elif has_aging:
            notice = "AGING PROVIDER OBSERVATION — VERIFY BEFORE TRAVEL"
        elif is_any_live:
            notice = "ESTIMATED IMPACT — BASED ON LIVE PROVIDER INCIDENT"
        else:
            notice = "Deterministic corridor estimate"

        # Calculate max freshness age in seconds across matched events
        max_age_seconds = 0
        now_dt = datetime.now(timezone.utc)
        for ev in all_matched_events:
            ev_dt = parse_iso_datetime(ev.observed_at)
            if ev_dt:
                age_s = max(0, int((now_dt - ev_dt).total_seconds()))
                if age_s > max_age_seconds:
                    max_age_seconds = age_s

        return JourneyDisruptionAssessment(
            journey_id=journey.id,
            is_disrupted=is_disrupted,
            highest_severity=highest_severity,
            overall_impact_level=overall_max_impact,
            total_estimated_delay_minutes=total_accumulated_delay_min,
            affected_segment_count=affected_count,
            critical_connection_risk_count=critical_risk_count,
            segment_impacts=segment_impacts,
            active_disruptions=all_matched_events,
            summary=summary,
            evaluated_at=now_dt.isoformat(),
            provenance=provenance,
            data_freshness_seconds=max_age_seconds if all_matched_events else 0,
            notice=notice,
        )

    def _assess_segment(
        self,
        segment: JourneySegmentSchema,
        matches: list[MatchedSegmentDisruption],
        next_segment: JourneySegmentSchema | None,
        prior_cumulative_delay_min: int,
    ) -> DisruptedSegmentImpact:
        """Computes impact on an individual segment and downstream transfer connection."""
        orig_dep_dt = parse_iso_datetime(segment.departure_time)
        orig_arr_dt = parse_iso_datetime(segment.arrival_time)

        now_dt = datetime.now(timezone.utc)
        dep_dt = orig_dep_dt or now_dt
        arr_dt = orig_arr_dt or (dep_dt + timedelta(minutes=segment.duration_minutes))

        if not matches:
            est_arr_dt = arr_dt + timedelta(minutes=prior_cumulative_delay_min)
            subsequent_risk, buffer_red = self._evaluate_downstream_transfer(
                current_est_arr_dt=est_arr_dt,
                next_segment=next_segment,
                segment_buffer_min=segment.transfer_buffer_minutes,
            )
            return DisruptedSegmentImpact(
                segment_id=segment.segment_id,
                sequence=segment.sequence,
                mode=segment.mode,
                impact_level="none",
                estimated_delay_minutes=0,
                original_departure_time=format_iso_datetime(dep_dt),
                original_arrival_time=format_iso_datetime(arr_dt),
                estimated_arrival_time=format_iso_datetime(est_arr_dt),
                matching_events=[],
                match_type="spatial_corridor",
                transfer_buffer_reduction_minutes=buffer_red,
                subsequent_transfer_risk=subsequent_risk,
                explanation="No disruptions detected on this leg.",
                provenance="deterministic_estimate",
            )

        max_event_delay = max((m.event.estimated_delay_minutes for m in matches), default=0)
        has_critical_event = any(
            m.event.event_type in ("road_closure", "service_cancellation")
            or m.event.severity == "critical"
            for m in matches
        )
        if has_critical_event and max_event_delay < 120:
            max_event_delay = max(max_event_delay, 120)

        if has_critical_event or max_event_delay >= 60:
            impact_level: DisruptionImpactLevel = "critical"
        elif max_event_delay >= 30:
            impact_level = "high"
        elif max_event_delay >= 15:
            impact_level = "moderate"
        elif max_event_delay > 0:
            impact_level = "low"
        else:
            impact_level = "low"

        new_est_arr_dt = arr_dt + timedelta(minutes=max_event_delay + prior_cumulative_delay_min)

        subsequent_risk, buffer_red = self._evaluate_downstream_transfer(
            current_est_arr_dt=new_est_arr_dt,
            next_segment=next_segment,
            segment_buffer_min=segment.transfer_buffer_minutes,
        )

        match_types = [m.match_type for m in matches]
        if "route_id_exact" in match_types:
            dominant_match_type = "route_id_exact"
        elif "stop_id_exact" in match_types:
            dominant_match_type = "stop_id_exact"
        elif "multimodal_corridor_correlation" in match_types:
            dominant_match_type = "multimodal_corridor_correlation"
        elif "exact_geometry" in match_types:
            dominant_match_type = "exact_geometry"
        elif "hub_approximate" in match_types:
            dominant_match_type = "hub_approximate"
        else:
            dominant_match_type = "spatial_corridor"

        explanations = [m.explanation for m in matches]
        explanation_text = " | ".join(explanations)
        if subsequent_risk in ("critical", "missed_estimated") and next_segment:
            explanation_text += (
                f" WARNING: Causes critical connection failure for {next_segment.mode} leg "
                f"at {segment.destination.name} (buffer eroded by {buffer_red} min)."
            )

        is_sim = any(m.event.provenance == "simulated" for m in matches)
        provenance: ProvenanceSourceType = "simulated" if is_sim else "deterministic_estimate"

        return DisruptedSegmentImpact(
            segment_id=segment.segment_id,
            sequence=segment.sequence,
            mode=segment.mode,
            impact_level=impact_level,
            estimated_delay_minutes=max_event_delay,
            original_departure_time=format_iso_datetime(dep_dt),
            original_arrival_time=format_iso_datetime(arr_dt),
            estimated_arrival_time=format_iso_datetime(new_est_arr_dt),
            matching_events=[m.event for m in matches],
            match_type=dominant_match_type,
            transfer_buffer_reduction_minutes=buffer_red,
            subsequent_transfer_risk=subsequent_risk,
            explanation=explanation_text,
            provenance=provenance,
        )

    def _evaluate_downstream_transfer(
        self,
        current_est_arr_dt: datetime,
        next_segment: JourneySegmentSchema | None,
        segment_buffer_min: int | None,
    ) -> tuple[ConnectionRiskLevel, int]:
        """Calculates buffer erosion and connection risk for the next leg."""
        if not next_segment:
            return "safe", 0

        next_dep_dt = parse_iso_datetime(next_segment.departure_time)
        if not next_dep_dt:
            return "unknown", 0

        required_buffer = segment_buffer_min if (segment_buffer_min and segment_buffer_min > 0) else 15
        available_buffer_minutes = int((next_dep_dt - current_est_arr_dt).total_seconds() / 60)
        buffer_reduction = max(0, required_buffer - available_buffer_minutes)

        if available_buffer_minutes < 0:
            return "critical", buffer_reduction
        elif available_buffer_minutes < required_buffer:
            return "at_risk", buffer_reduction
        else:
            return "safe", 0

    def _build_assessment_summary(
        self,
        is_disrupted: bool,
        affected_count: int,
        highest_severity: DisruptionSeverity,
        overall_max_impact: DisruptionImpactLevel,
        total_delay: int,
        critical_risk_count: int,
        events: list[DisruptionEvent],
        provenance: ProvenanceSourceType,
    ) -> str:
        if not is_disrupted:
            return "All route segments are clear. No disruptions detected along journey corridors."

        event_titles = ", ".join(e.title for e in events[:2])
        sim_prefix = "[SIMULATED] " if provenance == "simulated" else ""

        if critical_risk_count > 0:
            return (
                f"{sim_prefix}CRITICAL DISRUPTION: {event_titles} introduces an estimated +{total_delay} min delay across "
                f"{affected_count} leg(s), creating {critical_risk_count} missed connection risk(s). Journey recovery recommended."
            )
        else:
            return (
                f"{sim_prefix}DISRUPTION DETECTED: {event_titles} adds ~{total_delay} min delay "
                f"(severity: {highest_severity}, impact: {overall_max_impact}) across {affected_count} leg(s)."
            )


journey_impact_assessor = JourneyImpactAssessor()
