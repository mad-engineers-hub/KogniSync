import pytest
from datetime import datetime
from app.services.ai.gemini import GeminiIntentService
from app.services.ai.schemas import TravelContext, TravelIntent


@pytest.fixture
def service():
    return GeminiIntentService()


def test_case_1_chennai_to_udupi_extraction(service):
    """Test 1: Chennai to Udupi before 8 PM under ₹5000 with speed preference."""
    text = "I need to reach Udupi from Chennai tomorrow before 8 PM. My budget is ₹5000 and I prefer speed."
    context = TravelContext(origin="Bangalore", destination="Chennai", budget=3000, arrival_deadline="14:00")
    fixed_now = datetime(2026, 10, 29, 14, 0, 0)
    
    intent = service.parse_travel_intent(text=text, current_context=context, now=fixed_now)
    
    assert intent.origin.lower() == "chennai"
    assert intent.destination.lower() == "udupi"
    assert intent.date == "2026-10-30"
    assert intent.arrival_deadline == "20:00"
    assert intent.budget == 5000.0
    assert intent.time_priority >= 0.8


def test_case_2_chennai_to_delhi_extraction(service):
    """Test 2: Chennai to Delhi before 2 PM under ₹3000 saving money over speed."""
    text = "I need to reach Delhi from Chennai tomorrow before 2 PM. My budget is ₹3000 and I prefer saving money over speed."
    context = TravelContext(origin="Bangalore", destination="Chennai", budget=3000, arrival_deadline="14:00")
    fixed_now = datetime(2026, 10, 29, 14, 0, 0)
    
    intent = service.parse_travel_intent(text=text, current_context=context, now=fixed_now)
    
    assert intent.origin.lower() == "chennai"
    assert intent.destination.lower() == "delhi"
    assert intent.date == "2026-10-30"
    assert intent.arrival_deadline == "14:00"
    assert intent.budget == 3000.0
    assert intent.time_priority <= 0.4


def test_case_3_bangalore_to_goa_extraction(service):
    """Test 3: Bangalore to Goa under ₹5000."""
    text = "Trip to Goa from Bangalore this Saturday under ₹5000."
    context = None
    fixed_now = datetime(2026, 10, 29, 14, 0, 0)
    
    intent = service.parse_travel_intent(text=text, current_context=context, now=fixed_now)
    
    assert intent.origin.lower() == "bangalore"
    assert intent.destination.lower() == "goa"
    assert intent.budget == 5000.0


def test_case_4_partial_update_preserves_context(service):
    """Test 4: Partial update preserves existing context without corruption."""
    text = "Change destination to Mangalore"
    context = TravelContext(
        origin="Chennai",
        destination="Udupi",
        date="2026-10-30",
        arrival_deadline="20:00",
        budget=5000.0,
        time_priority=1.0,
    )
    fixed_now = datetime(2026, 10, 29, 14, 0, 0)
    
    intent = service.parse_travel_intent(text=text, current_context=context, now=fixed_now)
    
    assert intent.origin.lower() == "chennai"
    assert intent.destination.lower() == "mangalore"
    assert intent.date == "2026-10-30"
    assert intent.arrival_deadline == "20:00"
    assert intent.budget == 5000.0


def test_case_5_udayapalya_to_chennai_extraction(service):
    """Test 5: Udayapalya to Chennai before 5 PM under ₹5000 with speed preference."""
    text = "I want to travel from Udayapalya to Chennai tomorrow before 5 PM. My budget is ₹5,000 and I prefer speed."
    context = None
    fixed_now = datetime(2026, 10, 29, 14, 0, 0)
    
    intent = service.parse_travel_intent(text=text, current_context=context, now=fixed_now)
    
    assert "udayapalya" in intent.origin.lower()
    assert "chennai" in intent.destination.lower()
    assert intent.date == "2026-10-30"
    assert intent.arrival_deadline == "17:00"
    assert intent.budget == 5000.0
    assert intent.time_priority >= 0.8


