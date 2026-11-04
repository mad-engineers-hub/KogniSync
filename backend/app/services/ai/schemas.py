from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


class TravelContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    origin: Optional[str] = None
    destination: Optional[str] = None
    date: Optional[str] = None
    departure_time: Optional[str] = Field(default=None, validation_alias=AliasChoices("departure_time", "departureTime"))
    arrival_deadline: Optional[str] = Field(default=None, validation_alias=AliasChoices("arrival_deadline", "arrivalDeadline"))
    passengers: int = 1
    budget: Optional[float] = None
    currency: str = "INR"
    time_priority: float = Field(default=0.5, validation_alias=AliasChoices("time_priority", "timePriority"))
    comfort: float = 0.5
    sustainability: float = 0.5
    preferred_modes: List[str] = Field(default_factory=list, validation_alias=AliasChoices("preferred_modes", "preferredModes"))


class TravelIntent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    origin: Optional[str] = None
    destination: Optional[str] = None
    date: Optional[str] = None  # Format: YYYY-MM-DD
    departure_time: Optional[str] = Field(default=None, validation_alias=AliasChoices("departure_time", "departureTime"))  # Format: HH:mm (24-hour)
    arrival_deadline: Optional[str] = Field(default=None, validation_alias=AliasChoices("arrival_deadline", "arrivalDeadline"))  # Format: HH:mm (24-hour)
    passengers: int = 1
    budget: Optional[float] = None
    currency: str = "INR"
    time_priority: float = Field(default=0.5, validation_alias=AliasChoices("time_priority", "timePriority"))  # 0.0 = flexible/slow, 1.0 = fastest/urgent
    comfort: float = 0.5  # 0.0 = basic/budget, 1.0 = premium/luxury
    sustainability: float = 0.5  # 0.0 = any, 1.0 = eco-friendly
    preferred_modes: List[str] = Field(default_factory=list, validation_alias=AliasChoices("preferred_modes", "preferredModes"))  # flight, train, bus, cab, metro, walk
    intent_summary: Optional[str] = Field(default=None, validation_alias=AliasChoices("intent_summary", "intentSummary"))
    confidence: float = 0.0


class ParseIntentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    text: str
    current_context: Optional[TravelContext] = Field(default=None, validation_alias=AliasChoices("current_context", "currentContext"))


class ParseIntentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    intent: TravelIntent
