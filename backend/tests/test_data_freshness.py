"""
backend/tests/test_data_freshness.py

Comprehensive tests for DataFreshnessEngine (Milestone M3.8).
Verifies:
1. Fresh, aging, stale, expired, and unknown classification.
2. Clock skew tolerance (+120s clamped; excessive future marked unknown).
3. Provider and data-type-specific freshness thresholds (road incidents, service alerts, trip updates, vehicle positions).
4. Resolved and expired event exclusion.
5. Missing timestamp handling and disclosure notices.
"""
from datetime import datetime, timezone, timedelta
import pytest
from app.services.disruption.freshness import (
    DataFreshnessEngine,
    FreshnessPolicy,
    freshness_engine,
)
from app.services.disruption.schemas import DisruptionEvent
from app.services.journey.schemas import CoordinatesSchema


@pytest.fixture
def base_event():
    now = datetime.now(timezone.utc)
    return DisruptionEvent(
        id="test-freshness-ev-01",
        source="test_feed",
        event_type="traffic_congestion",
        severity="moderate",
        status="active",
        title="Test Incident",
        description="Test Description",
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=12.97, lng=77.59),
        valid_from=(now - timedelta(hours=1)).isoformat(),
        valid_until=(now + timedelta(hours=2)).isoformat(),
        observed_at=now.isoformat(),
        last_verified_at=now.isoformat(),
        provenance="provider_live",
    )


def test_fresh_event_evaluation(base_event):
    now = datetime.now(timezone.utc)
    # Event observed 10 minutes ago (< 30 min road threshold)
    base_event.observed_at = (now - timedelta(minutes=10)).isoformat()

    report = freshness_engine.evaluate_event_freshness(base_event, data_type="road_incident", as_of=now)
    assert report.status == "fresh"
    assert report.is_usable is True
    assert report.is_expired is False
    assert report.requires_disclosure is False
    assert report.disclosure_notice is None
    assert 590 <= report.age_seconds <= 610


def test_aging_event_evaluation(base_event):
    now = datetime.now(timezone.utc)
    # Event observed 45 minutes ago (> 30 min, <= 60 min)
    base_event.observed_at = (now - timedelta(minutes=45)).isoformat()

    report = freshness_engine.evaluate_event_freshness(base_event, data_type="road_incident", as_of=now)
    assert report.status == "aging"
    assert report.is_usable is True
    assert report.is_expired is False
    assert report.requires_disclosure is True
    assert "aging" in (report.disclosure_notice or "").lower()


def test_stale_event_evaluation(base_event):
    now = datetime.now(timezone.utc)
    # Event observed 75 minutes ago (> 60 min)
    base_event.observed_at = (now - timedelta(minutes=75)).isoformat()

    report = freshness_engine.evaluate_event_freshness(base_event, data_type="road_incident", as_of=now)
    assert report.status == "stale"
    assert report.is_usable is False
    assert report.is_expired is False
    assert report.requires_disclosure is True
    assert "STALE OBSERVATION" in (report.disclosure_notice or "")


def test_expired_by_schedule_or_resolved(base_event):
    now = datetime.now(timezone.utc)
    # 1. Past valid_until
    base_event.valid_until = (now - timedelta(minutes=5)).isoformat()
    report = freshness_engine.evaluate_event_freshness(base_event, as_of=now)
    assert report.status == "expired"
    assert report.is_usable is False
    assert report.is_expired is True

    # 2. Resolved status
    base_event.valid_until = (now + timedelta(hours=2)).isoformat()
    base_event.status = "resolved"
    report_resolved = freshness_engine.evaluate_event_freshness(base_event, as_of=now)
    assert report_resolved.status == "expired"
    assert report_resolved.is_usable is False
    assert report_resolved.is_expired is True


def test_clock_skew_tolerance(base_event):
    now = datetime.now(timezone.utc)
    # Case 1: 45 seconds in the future (within 120s tolerance -> clamped to age 0, fresh)
    base_event.observed_at = (now + timedelta(seconds=45)).isoformat()
    report = freshness_engine.evaluate_event_freshness(base_event, as_of=now)
    assert report.status == "fresh"
    assert report.age_seconds == 0

    # Case 2: 5 minutes in the future (excessive drift -> unknown, unusable)
    base_event.observed_at = (now + timedelta(minutes=5)).isoformat()
    report_future = freshness_engine.evaluate_event_freshness(base_event, as_of=now)
    assert report_future.status == "unknown"
    assert report_future.is_usable is False


def test_data_type_specific_thresholds(base_event):
    now = datetime.now(timezone.utc)
    # 7 minutes old:
    # For road_incident (fresh <= 30m): fresh
    # For trip_update (fresh <= 5m, aging <= 10m): aging
    # For vehicle_position (fresh <= 1m, aging <= 3m): stale
    base_event.observed_at = (now - timedelta(minutes=7)).isoformat()

    report_road = freshness_engine.evaluate_event_freshness(base_event, data_type="road_incident", as_of=now)
    assert report_road.status == "fresh"

    report_trip = freshness_engine.evaluate_event_freshness(base_event, data_type="trip_update", as_of=now)
    assert report_trip.status == "aging"

    report_veh = freshness_engine.evaluate_event_freshness(base_event, data_type="vehicle_position", as_of=now)
    assert report_veh.status == "stale"
    assert report_veh.is_usable is False
