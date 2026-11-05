"""
backend/app/services/journey/hubs.py

City hubs, locality mapping, corridor distance estimation, and localized transit operator registry.
Ported and hardened from canonical frontend model for authoritative backend composition.
"""
import math
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from app.services.journey.schemas import CoordinatesSchema, LocationSchema


def slugify(text: str) -> str:
    cleaned = (text or "").lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    return cleaned.strip("-")


@dataclass
class HubProfile:
    city: str
    lat: float
    lng: float
    railway_name: str
    railway_code: str | None
    railway_lat: float
    railway_lng: float
    airport_name: str
    airport_code: str | None
    airport_lat: float
    airport_lng: float
    bus_name: str
    bus_lat: float
    bus_lng: float
    metro_name: str
    metro_lat: float
    metro_lng: float
    has_metro: bool


CITY_HUB_REGISTRY: dict[str, HubProfile] = {
    "bangalore": HubProfile(
        city="Bangalore",
        lat=12.9716,
        lng=77.5946,
        railway_name="Bangalore Railway Station (KSR / Cantt)",
        railway_code="SBC",
        railway_lat=12.9781,
        railway_lng=77.5694,
        airport_name="Kempegowda International Airport (BLR)",
        airport_code="BLR",
        airport_lat=13.1986,
        airport_lng=77.7066,
        bus_name="Majestic Bus Terminal (KSRTC/BMTC)",
        bus_lat=12.9774,
        bus_lng=77.5713,
        metro_name="Nadaprabhu Kempegowda Majestic Metro",
        metro_lat=12.9756,
        metro_lng=77.5728,
        has_metro=True,
    ),
    "chennai": HubProfile(
        city="Chennai",
        lat=13.0827,
        lng=80.2707,
        railway_name="Chennai Central Railway Station",
        railway_code="MAS",
        railway_lat=13.0827,
        railway_lng=80.2755,
        airport_name="Chennai International Airport (MAA)",
        airport_code="MAA",
        airport_lat=12.9941,
        airport_lng=80.1709,
        bus_name="Koyambedu Bus Terminal (CMBT)",
        bus_lat=13.0682,
        bus_lng=80.2052,
        metro_name="Central Metro Interchange Hub",
        metro_lat=13.0818,
        metro_lng=80.2735,
        has_metro=True,
    ),
    "mumbai": HubProfile(
        city="Mumbai",
        lat=19.0760,
        lng=72.8777,
        railway_name="Chhatrapati Shivaji Maharaj Terminus (CSMT)",
        railway_code="CSMT",
        railway_lat=18.9401,
        railway_lng=72.8354,
        airport_name="Chhatrapati Shivaji International Airport (BOM)",
        airport_code="BOM",
        airport_lat=19.0896,
        airport_lng=72.8656,
        bus_name="Dadar Intercity Bus Terminal",
        bus_lat=19.0178,
        bus_lng=72.8478,
        metro_name="Andheri Metro Interchange",
        metro_lat=19.1197,
        metro_lng=72.8464,
        has_metro=True,
    ),
    "delhi": HubProfile(
        city="Delhi",
        lat=28.6139,
        lng=77.2090,
        railway_name="New Delhi Railway Station (NDLS)",
        railway_code="NDLS",
        railway_lat=28.6429,
        railway_lng=77.2195,
        airport_name="Indira Gandhi International Airport (DEL)",
        airport_code="DEL",
        airport_lat=28.5562,
        airport_lng=77.1000,
        bus_name="ISBT Kashmere Gate Terminal",
        bus_lat=28.6675,
        bus_lng=77.2289,
        metro_name="Rajiv Chowk Metro Hub",
        metro_lat=28.6328,
        metro_lng=77.2197,
        has_metro=True,
    ),
    "goa": HubProfile(
        city="Goa",
        lat=15.2993,
        lng=74.1240,
        railway_name="Madgaon Railway Junction",
        railway_code="MAO",
        railway_lat=15.2736,
        railway_lng=73.9582,
        airport_name="Goa Dabolim Airport (GOI)",
        airport_code="GOI",
        airport_lat=15.3808,
        airport_lng=73.8314,
        bus_name="Panaji KADAMBA Bus Stand",
        bus_lat=15.4989,
        bus_lng=73.8278,
        metro_name="Goa Coastal Rapid EV Transit",
        metro_lat=15.4950,
        metro_lng=73.8300,
        has_metro=False,
    ),
    "udupi": HubProfile(
        city="Udupi",
        lat=13.3409,
        lng=74.7421,
        railway_name="Udupi Railway Station",
        railway_code="UD",
        railway_lat=13.3409,
        railway_lng=74.7421,
        airport_name="Mangalore International Airport (IXE)",
        airport_code="IXE",
        airport_lat=12.9613,
        airport_lng=74.8901,
        bus_name="Udupi Central Bus Stand",
        bus_lat=13.3415,
        bus_lng=74.7473,
        metro_name="Coastal Green Rapid EV Shuttle",
        metro_lat=13.3420,
        metro_lng=74.7450,
        has_metro=False,
    ),
    "mangalore": HubProfile(
        city="Mangalore",
        lat=12.9141,
        lng=74.8560,
        railway_name="Mangaluru Central Railway Station",
        railway_code="MAQ",
        railway_lat=12.8631,
        railway_lng=74.8427,
        airport_name="Mangalore International Airport (IXE)",
        airport_code="IXE",
        airport_lat=12.9613,
        airport_lng=74.8901,
        bus_name="KSRTC Bejai Bus Stand",
        bus_lat=12.8872,
        bus_lng=74.8492,
        metro_name="Mangaluru Coastal EV Express",
        metro_lat=12.8700,
        metro_lng=74.8500,
        has_metro=False,
    ),
    "hyderabad": HubProfile(
        city="Hyderabad",
        lat=17.3850,
        lng=78.4867,
        railway_name="Secunderabad Railway Station",
        railway_code="SC",
        railway_lat=17.4334,
        railway_lng=78.5042,
        airport_name="Rajiv Gandhi International Airport (HYD)",
        airport_code="HYD",
        airport_lat=17.2403,
        airport_lng=78.4294,
        bus_name="MGBS Central Bus Station",
        bus_lat=17.3789,
        bus_lng=78.4812,
        metro_name="Ameerpet Metro Interchange",
        metro_lat=17.4375,
        metro_lng=78.4483,
        has_metro=True,
    ),
    "pune": HubProfile(
        city="Pune",
        lat=18.5204,
        lng=73.8567,
        railway_name="Pune Railway Junction",
        railway_code="PUNE",
        railway_lat=18.5284,
        railway_lng=73.8744,
        airport_name="Pune International Airport (PNQ)",
        airport_code="PNQ",
        airport_lat=18.5822,
        airport_lng=73.9197,
        bus_name="Shivaji Nagar Bus Terminus",
        bus_lat=18.5314,
        bus_lng=73.8553,
        metro_name="Civil Court Metro Interchange",
        metro_lat=18.5308,
        metro_lng=73.8567,
        has_metro=True,
    ),
    "kolkata": HubProfile(
        city="Kolkata",
        lat=22.5726,
        lng=88.3639,
        railway_name="Howrah Railway Station",
        railway_code="HWH",
        railway_lat=22.5839,
        railway_lng=88.3426,
        airport_name="Netaji Subhash Chandra Bose Airport (CCU)",
        airport_code="CCU",
        airport_lat=22.6547,
        airport_lng=88.4467,
        bus_name="Esplanade Bus Terminus",
        bus_lat=22.5647,
        bus_lng=88.3517,
        metro_name="Esplanade Metro Interchange",
        metro_lat=22.5640,
        metro_lng=88.3510,
        has_metro=True,
    ),
    "jaipur": HubProfile(
        city="Jaipur",
        lat=26.9124,
        lng=75.7873,
        railway_name="Jaipur Railway Junction",
        railway_code="JP",
        railway_lat=26.9196,
        railway_lng=75.7878,
        airport_name="Jaipur International Airport (JAI)",
        airport_code="JAI",
        airport_lat=26.8289,
        airport_lng=75.8056,
        bus_name="Sindhi Camp Central Bus Stand",
        bus_lat=26.9239,
        bus_lng=75.7981,
        metro_name="Sindhi Camp Metro Station",
        metro_lat=26.9230,
        metro_lng=75.7980,
        has_metro=True,
    ),
    "ahmedabad": HubProfile(
        city="Ahmedabad",
        lat=23.0225,
        lng=72.5714,
        railway_name="Ahmedabad Junction (Kalupur)",
        railway_code="ADI",
        railway_lat=23.0232,
        railway_lng=72.6002,
        airport_name="Sardar Vallabhbhai Patel Airport (AMD)",
        airport_code="AMD",
        airport_lat=23.0772,
        airport_lng=72.6347,
        bus_name="Geeta Mandir Central Bus Terminus",
        bus_lat=23.0125,
        bus_lng=72.5936,
        metro_name="Old High Court Metro Interchange",
        metro_lat=23.0360,
        metro_lng=72.5620,
        has_metro=True,
    ),
    "kochi": HubProfile(
        city="Kochi",
        lat=9.9312,
        lng=76.2673,
        railway_name="Ernakulam Junction (South)",
        railway_code="ERS",
        railway_lat=9.9678,
        railway_lng=76.2891,
        airport_name="Cochin International Airport (COK)",
        airport_code="COK",
        airport_lat=10.1518,
        airport_lng=76.4019,
        bus_name="KSRTC Central Bus Stand Ernakulam",
        bus_lat=9.9723,
        bus_lng=76.2872,
        metro_name="MG Road Metro Station",
        metro_lat=9.9730,
        metro_lng=76.2820,
        has_metro=True,
    ),
    "mysore": HubProfile(
        city="Mysore",
        lat=12.2958,
        lng=76.6394,
        railway_name="Mysuru Junction Railway Station",
        railway_code="MYS",
        railway_lat=12.3163,
        railway_lng=76.6455,
        airport_name="Mysore Mandakalli Airport (MYQ)",
        airport_code="MYQ",
        airport_lat=12.2300,
        airport_lng=76.6500,
        bus_name="Mysore KSRTC Suburb Bus Stand",
        bus_lat=12.3106,
        bus_lng=76.6567,
        metro_name="Mysuru City Bus Transit Hub",
        metro_lat=12.3080,
        metro_lng=76.6530,
        has_metro=False,
    ),
}

LOCALITY_TO_CITY_MAP: dict[str, str] = {
    # Bangalore
    "udayapalya": "bangalore",
    "kanakapura": "bangalore",
    "kanakapura road": "bangalore",
    "whitefield": "bangalore",
    "koramangala": "bangalore",
    "indiranagar": "bangalore",
    "hsr": "bangalore",
    "hsr layout": "bangalore",
    "jayanagar": "bangalore",
    "marathahalli": "bangalore",
    "electronic city": "bangalore",
    "btm": "bangalore",
    "btm layout": "bangalore",
    "yelahanka": "bangalore",
    "hebbal": "bangalore",
    "banashankari": "bangalore",
    "bellandur": "bangalore",
    # Chennai
    "guindy": "chennai",
    "t nagar": "chennai",
    "t. nagar": "chennai",
    "adyar": "chennai",
    "velachery": "chennai",
    "anna nagar": "chennai",
    "tambaram": "chennai",
    "omr": "chennai",
    "porur": "chennai",
    "mylapore": "chennai",
    "marina": "chennai",
    # Mumbai
    "bkc": "mumbai",
    "bandra": "mumbai",
    "andheri": "mumbai",
    "powai": "mumbai",
    "dadar": "mumbai",
    "thane": "mumbai",
    "colaba": "mumbai",
    "borivali": "mumbai",
    # Delhi
    "gurgaon": "delhi",
    "gurugram": "delhi",
    "noida": "delhi",
    "connaught place": "delhi",
    "dwarka": "delhi",
    "saket": "delhi",
    # Goa
    "panaji": "goa",
    "calangute": "goa",
    "baga": "goa",
    "candolim": "goa",
    "margao": "goa",
    "anjuna": "goa",
    "vasco": "goa",
    # Udupi
    "manipal": "udupi",
    "malpe": "udupi",
    "kaup": "udupi",
    "kundapura": "udupi",
    "karkala": "udupi",
}

CORRIDOR_DISTANCES: dict[str, int] = {
    "bangalore-chennai": 350,
    "chennai-bangalore": 350,
    "bangalore-goa": 560,
    "goa-bangalore": 560,
    "chennai-udupi": 720,
    "udupi-chennai": 720,
    "bangalore-udupi": 410,
    "udupi-bangalore": 410,
    "delhi-mumbai": 1385,
    "mumbai-delhi": 1385,
    "mumbai-pune": 150,
    "pune-mumbai": 150,
    "delhi-jaipur": 280,
    "jaipur-delhi": 280,
    "bangalore-hyderabad": 570,
    "hyderabad-bangalore": 570,
    "mumbai-goa": 580,
    "goa-mumbai": 580,
    "bangalore-mysore": 145,
    "mysore-bangalore": 145,
}


@dataclass
class ResolvedHubContext:
    raw_location: str
    is_locality: bool
    parent_city: str
    user_node: LocationSchema
    railway_hub: LocationSchema
    airport_hub: LocationSchema
    bus_hub: LocationSchema
    metro_hub: LocationSchema


def resolve_hub_context(location_str: str, is_origin: bool) -> ResolvedHubContext:
    raw = (location_str or "").strip()
    lower = raw.lower()

    parent_city_key = LOCALITY_TO_CITY_MAP.get(lower)
    is_locality = bool(parent_city_key)

    if not parent_city_key:
        if lower in CITY_HUB_REGISTRY:
            parent_city_key = lower
            is_locality = False
        else:
            for loc, city in LOCALITY_TO_CITY_MAP.items():
                if loc in lower:
                    parent_city_key = city
                    is_locality = True
                    break
            if not parent_city_key:
                for city in CITY_HUB_REGISTRY.keys():
                    if city in lower:
                        parent_city_key = city
                        is_locality = False
                        break

    capitalized_raw = raw.capitalize() if raw else ("Bangalore" if is_origin else "Chennai")

    if parent_city_key and parent_city_key in CITY_HUB_REGISTRY:
        profile = CITY_HUB_REGISTRY[parent_city_key]
    else:
        dynamic_city = capitalized_raw
        def_lat = 13.0 if is_origin else 15.0
        def_lng = 77.6 if is_origin else 74.5
        profile = HubProfile(
            city=dynamic_city,
            lat=def_lat,
            lng=def_lng,
            railway_name=f"{dynamic_city} Railway Junction",
            railway_code=None,
            railway_lat=def_lat,
            railway_lng=def_lng,
            airport_name=f"{dynamic_city} Regional Airport",
            airport_code=None,
            airport_lat=def_lat + 0.12,
            airport_lng=def_lng + 0.08,
            bus_name=f"{dynamic_city} Central Intercity Bus Terminal",
            bus_lat=def_lat - 0.02,
            bus_lng=def_lng,
            metro_name=f"{dynamic_city} City Transit Center",
            metro_lat=def_lat,
            metro_lng=def_lng,
            has_metro=False,
        )
        is_locality = False

    user_node = LocationSchema(
        id=f"loc-usr-{'orig' if is_origin else 'dest'}-{slugify(raw or profile.city)}",
        name=f"{capitalized_raw}" if is_locality else f"{profile.city} City Hub",
        city=f"{capitalized_raw} ({profile.city})" if is_locality else profile.city,
        type="address" if is_locality else "landmark",
        coordinates=CoordinatesSchema(
            lat=round(profile.lat + (-0.04 if is_origin else 0.04), 4),
            lng=round(profile.lng + (-0.03 if is_origin else 0.03), 4),
        ),
    )

    railway_hub = LocationSchema(
        id=f"loc-hub-rail-{slugify(profile.city)}",
        name=profile.railway_name,
        city=profile.city,
        code=profile.railway_code,
        type="railway_station",
        coordinates=CoordinatesSchema(lat=profile.railway_lat, lng=profile.railway_lng),
    )

    airport_hub = LocationSchema(
        id=f"loc-hub-air-{slugify(profile.city)}",
        name=profile.airport_name,
        city=profile.city,
        code=profile.airport_code,
        type="airport",
        coordinates=CoordinatesSchema(lat=profile.airport_lat, lng=profile.airport_lng),
    )

    bus_hub = LocationSchema(
        id=f"loc-hub-bus-{slugify(profile.city)}",
        name=profile.bus_name,
        city=profile.city,
        type="bus_terminal",
        coordinates=CoordinatesSchema(lat=profile.bus_lat, lng=profile.bus_lng),
    )

    metro_hub = LocationSchema(
        id=f"loc-hub-metro-{slugify(profile.city)}",
        name=profile.metro_name,
        city=profile.city,
        type="metro_station",
        coordinates=CoordinatesSchema(lat=profile.metro_lat, lng=profile.metro_lng),
    )

    return ResolvedHubContext(
        raw_location=raw,
        is_locality=is_locality,
        parent_city=profile.city,
        user_node=user_node,
        railway_hub=railway_hub,
        airport_hub=airport_hub,
        bus_hub=bus_hub,
        metro_hub=metro_hub,
    )


def estimate_corridor_distance_km(origin_city: str, dest_city: str) -> int:
    o = slugify(origin_city)
    d = slugify(dest_city)
    key = f"{o}-{d}"
    if key in CORRIDOR_DISTANCES:
        return CORRIDOR_DISTANCES[key]

    p1 = CITY_HUB_REGISTRY.get(o)
    p2 = CITY_HUB_REGISTRY.get(d)
    if p1 and p2:
        R = 6371.0
        d_lat = math.radians(p2.lat - p1.lat)
        d_lon = math.radians(p2.lng - p1.lng)
        a = (
            math.sin(d_lat / 2.0) ** 2
            + math.cos(math.radians(p1.lat)) * math.cos(math.radians(p2.lat)) * math.sin(d_lon / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return max(90, int(round(R * c * 1.25)))

    return 450


def parse_target_arrival(deadline_str: str | None) -> tuple[int, int]:
    if not deadline_str:
        return (20, 0)
    cleaned = deadline_str.strip().lower()
    is_pm = "pm" in cleaned
    is_am = "am" in cleaned
    digits = re.sub(r"(am|pm|arrive|by|before|\s)", "", cleaned)
    parts = digits.split(":")
    if parts and parts[0]:
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            if is_pm and h < 12:
                h += 12
            if is_am and h == 12:
                h = 0
            return (min(23, max(0, h)), min(59, max(0, m)))
        except ValueError:
            pass
    return (20, 0)


def build_iso_date(base_date_str: str, hour: int, minute: int) -> datetime:
    try:
        parts = [int(p) for p in base_date_str.split("-")]
        if len(parts) == 3:
            return datetime(parts[0], parts[1], parts[2], hour, minute, 0, tzinfo=timezone.utc)
    except Exception:
        pass
    return datetime(2026, 10, 30, hour, minute, 0, tzinfo=timezone.utc)


def get_local_transit_operators(city_name: str) -> dict[str, dict[str, str]]:
    c = (city_name or "").lower()
    if "bangalore" in c:
        return {
            "cab": {"provider": "KogniSync Priority SyncCab (Bangalore)", "vehicle_name": "Airport Express Sedan"},
            "rapido": {"provider": "Rapido QuickSync Bangalore", "vehicle_name": "Rapido Auto / Bike Express"},
            "bus": {"provider": "BMTC City Feeder (Route 215)", "vehicle_name": "Electric City Bus"},
            "metro": {"provider": "Namma Metro Green Line", "vehicle_name": "Metro Electric Transit"},
        }
    if "chennai" in c:
        return {
            "cab": {"provider": "KogniSync FastTrack Cab (Chennai)", "vehicle_name": "Airport Express Sedan"},
            "rapido": {"provider": "Rapido QuickSync Chennai", "vehicle_name": "Rapido Auto / Bike Express"},
            "bus": {"provider": "MTC Metro Feeder Bus", "vehicle_name": "City Transit Line"},
            "metro": {"provider": "Chennai Metro Blue Line", "vehicle_name": "Metro Electric Express"},
        }
    if "mumbai" in c:
        return {
            "cab": {"provider": "KogniSync CoolCab (Mumbai)", "vehicle_name": "Premier City Sedan"},
            "rapido": {"provider": "Rapido QuickSync Mumbai", "vehicle_name": "Rapido Auto / Bike Express"},
            "bus": {"provider": "BEST Electric City Feeder", "vehicle_name": "Electric Single-Decker Bus"},
            "metro": {"provider": "Mumbai Metro Line 2A", "vehicle_name": "Metro Electric Transit"},
        }
    if "delhi" in c:
        return {
            "cab": {"provider": "KogniSync Express Cab (Delhi NCR)", "vehicle_name": "Premier EV Sedan"},
            "rapido": {"provider": "Rapido QuickSync Delhi", "vehicle_name": "Rapido Auto / Bike Express"},
            "bus": {"provider": "DTC Electric Feeder", "vehicle_name": "Low-Floor Electric Bus"},
            "metro": {"provider": "Delhi Metro Airport Express", "vehicle_name": "Rapid Metro Line"},
        }
    if "goa" in c:
        return {
            "cab": {"provider": "GoaMiles Express Taxi", "vehicle_name": "Airport Shuttle Sedan"},
            "rapido": {"provider": "Goa Coastal Bike Taxi", "vehicle_name": "Rapid Motorbike Pilot"},
            "bus": {"provider": "Kadamba Transport Shuttle", "vehicle_name": "Kadamba EV Feeder"},
            "metro": {"provider": "Goa Coastal Rapid EV Shuttle", "vehicle_name": "Zero-Emission EV Transit"},
        }
    if "udupi" in c or "mangalore" in c:
        return {
            "cab": {"provider": "Coastal Express Taxi (Udupi/Mangalore)", "vehicle_name": "Inter-City Sedan"},
            "rapido": {"provider": "Coastal Auto QuickSync", "vehicle_name": "Rapid City Auto"},
            "bus": {"provider": "Udupi-Manipal Express City Bus", "vehicle_name": "City Feeder Bus"},
            "metro": {"provider": "Coastal Green Rapid EV Shuttle", "vehicle_name": "Zero-Emission EV Shuttle"},
        }
    if "hyderabad" in c:
        return {
            "cab": {"provider": "KogniSync MetroCab (Hyderabad)", "vehicle_name": "Airport Express Sedan"},
            "rapido": {"provider": "Rapido QuickSync Hyderabad", "vehicle_name": "Rapido Auto / Bike"},
            "bus": {"provider": "TSRTC Pushpak Airport Liner", "vehicle_name": "Electric AC Liner"},
            "metro": {"provider": "Hyderabad Metro Red Line", "vehicle_name": "Metro Electric Transit"},
        }
    if "pune" in c:
        return {
            "cab": {"provider": "KogniSync Express Cab (Pune)", "vehicle_name": "City Sedan"},
            "rapido": {"provider": "Rapido QuickSync Pune", "vehicle_name": "Rapido Auto"},
            "bus": {"provider": "PMPML Rainbow BRTS Feeder", "vehicle_name": "BRTS Electric Bus"},
            "metro": {"provider": "Pune Metro Aqua Line", "vehicle_name": "Metro Electric Transit"},
        }

    return {
        "cab": {"provider": f"KogniSync Priority SyncCab ({city_name})", "vehicle_name": "Priority City Sedan"},
        "rapido": {"provider": f"Rapido QuickSync {city_name}", "vehicle_name": "Rapido Auto / Bike"},
        "bus": {"provider": f"{city_name} City Feeder Bus", "vehicle_name": "City Transit Line"},
        "metro": {"provider": f"{city_name} Rapid EV Shuttle", "vehicle_name": "Zero-Emission EV Transit"},
    }
