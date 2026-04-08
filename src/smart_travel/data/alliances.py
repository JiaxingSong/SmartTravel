"""Airline alliance membership, IATA region classification, and credit card transfer partners.

This module provides the static reference data needed to determine which loyalty
programs can book a given flight (via alliance partnerships) and how to acquire
the miles (via credit card transfer partners).
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Alliance membership
# ---------------------------------------------------------------------------

ALLIANCES: dict[str, list[str]] = {
    "star_alliance": [
        "united", "ana", "lufthansa", "swiss", "austrian", "air_canada",
        "singapore", "turkish", "eva", "tap", "thai", "air_india",
        "avianca", "copa", "ethiopian", "lot", "sas", "asiana",
        "aegean", "air_china", "air_new_zealand", "brussels", "croatia",
        "egyptair", "south_african",
    ],
    "oneworld": [
        "american", "british_airways", "cathay", "qantas", "jal",
        "iberia", "finnair", "malaysia", "qatar", "royal_jordanian",
        "srilankan", "alaska", "oman_air", "fiji_airways",
    ],
    "skyteam": [
        "delta", "air_france", "klm", "korean_air", "china_airlines",
        "garuda", "aeromexico", "vietnam", "xiamen", "china_eastern",
        "czech", "ita", "kenya", "middle_east", "saudia", "tarom",
    ],
    "independent": [
        "southwest", "jetblue", "spirit", "frontier", "hawaiian",
    ],
}

# Reverse lookup: airline → alliance
AIRLINE_ALLIANCE: dict[str, str] = {}
for _alliance, _airlines in ALLIANCES.items():
    for _a in _airlines:
        AIRLINE_ALLIANCE[_a] = _alliance


# ---------------------------------------------------------------------------
# Airline display names + IATA codes
# ---------------------------------------------------------------------------

AIRLINE_INFO: dict[str, dict[str, str]] = {
    # North America
    "united":          {"name": "United Airlines",     "iata": "UA"},
    "delta":           {"name": "Delta Air Lines",     "iata": "DL"},
    "american":        {"name": "American Airlines",   "iata": "AA"},
    "alaska":          {"name": "Alaska Airlines",     "iata": "AS"},
    "air_canada":      {"name": "Air Canada",          "iata": "AC"},
    "southwest":       {"name": "Southwest Airlines",  "iata": "WN"},
    "jetblue":         {"name": "JetBlue Airways",     "iata": "B6"},
    "spirit":          {"name": "Spirit Airlines",     "iata": "NK"},
    "frontier":        {"name": "Frontier Airlines",   "iata": "F9"},
    "hawaiian":        {"name": "Hawaiian Airlines",   "iata": "HA"},
    # Asia
    "ana":             {"name": "ANA",                 "iata": "NH"},
    "jal":             {"name": "Japan Airlines",      "iata": "JL"},
    "cathay":          {"name": "Cathay Pacific",      "iata": "CX"},
    "singapore":       {"name": "Singapore Airlines",  "iata": "SQ"},
    "korean_air":      {"name": "Korean Air",          "iata": "KE"},
    "eva":             {"name": "EVA Air",             "iata": "BR"},
    "china_airlines":  {"name": "China Airlines",      "iata": "CI"},
    "thai":            {"name": "Thai Airways",        "iata": "TG"},
    "malaysia":        {"name": "Malaysia Airlines",   "iata": "MH"},
    "air_india":       {"name": "Air India",           "iata": "AI"},
    "asiana":          {"name": "Asiana Airlines",     "iata": "OZ"},
    "china_eastern":   {"name": "China Eastern",       "iata": "MU"},
    "vietnam":         {"name": "Vietnam Airlines",    "iata": "VN"},
    "garuda":          {"name": "Garuda Indonesia",    "iata": "GA"},
    # Europe
    "british_airways": {"name": "British Airways",     "iata": "BA"},
    "lufthansa":       {"name": "Lufthansa",           "iata": "LH"},
    "swiss":           {"name": "SWISS",               "iata": "LX"},
    "austrian":        {"name": "Austrian Airlines",   "iata": "OS"},
    "air_france":      {"name": "Air France",          "iata": "AF"},
    "klm":             {"name": "KLM",                 "iata": "KL"},
    "turkish":         {"name": "Turkish Airlines",    "iata": "TK"},
    "iberia":          {"name": "Iberia",              "iata": "IB"},
    "virgin_atlantic": {"name": "Virgin Atlantic",     "iata": "VS"},
    "sas":             {"name": "SAS",                 "iata": "SK"},
    "finnair":         {"name": "Finnair",             "iata": "AY"},
    "tap":             {"name": "TAP Air Portugal",    "iata": "TP"},
    "ita":             {"name": "ITA Airways",         "iata": "AZ"},
    "lot":             {"name": "LOT Polish Airlines", "iata": "LO"},
    "aegean":          {"name": "Aegean Airlines",     "iata": "A3"},
    "avianca":         {"name": "Avianca",             "iata": "AV"},
    "copa":            {"name": "Copa Airlines",       "iata": "CM"},
    "qatar":           {"name": "Qatar Airways",       "iata": "QR"},
    "qantas":          {"name": "Qantas",              "iata": "QF"},
    "aeromexico":      {"name": "Aeromexico",          "iata": "AM"},
    "ethiopian":       {"name": "Ethiopian Airlines",  "iata": "ET"},
}

# Reverse: IATA code → airline key
IATA_TO_KEY: dict[str, str] = {v["iata"]: k for k, v in AIRLINE_INFO.items()}

# Common display-name aliases → canonical key
AIRLINE_NAME_ALIASES: dict[str, str] = {
    "united airlines": "united",
    "delta air lines": "delta",
    "delta airlines": "delta",
    "american airlines": "american",
    "alaska airlines": "alaska",
    "air canada": "air_canada",
    "southwest airlines": "southwest",
    "jetblue airways": "jetblue",
    "british airways": "british_airways",
    "cathay pacific": "cathay",
    "singapore airlines": "singapore",
    "korean air": "korean_air",
    "eva air": "eva",
    "china airlines": "china_airlines",
    "thai airways": "thai",
    "malaysia airlines": "malaysia",
    "air india": "air_india",
    "japan airlines": "jal",
    "turkish airlines": "turkish",
    "virgin atlantic": "virgin_atlantic",
    "air france": "air_france",
    "tap air portugal": "tap",
    "tap portugal": "tap",
    "lot polish": "lot",
    "aegean airlines": "aegean",
    "china eastern": "china_eastern",
    "vietnam airlines": "vietnam",
    "garuda indonesia": "garuda",
    "ita airways": "ita",
    "qatar airways": "qatar",
    "aa": "american",
}


def normalize_airline(name: str) -> str:
    """Map an airline display name or IATA code to its canonical key."""
    key = name.strip().lower()
    if key in AIRLINE_INFO:
        return key
    if key.upper() in IATA_TO_KEY:
        return IATA_TO_KEY[key.upper()]
    return AIRLINE_NAME_ALIASES.get(key, key)


def get_alliance(airline: str) -> str:
    """Return the alliance for an airline, or 'independent'."""
    return AIRLINE_ALLIANCE.get(normalize_airline(airline), "independent")


def get_alliance_partners(airline: str) -> list[str]:
    """Return all airlines in the same alliance (excluding the given airline)."""
    key = normalize_airline(airline)
    alliance = AIRLINE_ALLIANCE.get(key, "independent")
    if alliance == "independent":
        return []
    return [a for a in ALLIANCES.get(alliance, []) if a != key]


# ---------------------------------------------------------------------------
# Special (non-alliance) partner relationships
# ---------------------------------------------------------------------------

SPECIAL_PARTNERS: dict[str, list[str]] = {
    # Programs that can book flights on airlines outside their alliance
    "alaska":          ["jal", "cathay", "finnair", "qantas", "icelandair",
                        "korean_air", "singapore", "emirates"],
    "virgin_atlantic": ["ana", "delta", "air_france"],
    "jetblue":         ["hawaiian", "icelandair"],
    "korean_air":      ["alaska", "delta", "hawaiian"],
    "singapore":       ["virgin_atlantic", "virgin_australia"],
    "air_canada":      ["gulf_air", "vistara"],
    "cathay":          ["alaska"],
    "qantas":          ["alaska", "jetstar", "emirates"],
}


def get_bookable_programs(operating_airline: str) -> list[str]:
    """Return all loyalty programs that can book flights on this airline.

    Includes: own program, alliance partners' programs, special partners.
    """
    key = normalize_airline(operating_airline)
    programs = [key]  # own program

    # Alliance partners
    alliance = AIRLINE_ALLIANCE.get(key, "independent")
    if alliance != "independent":
        programs.extend(ALLIANCES.get(alliance, []))

    # Special partners (reverse lookup: who can book on this airline?)
    for program, partners in SPECIAL_PARTNERS.items():
        if key in partners and program not in programs:
            programs.append(program)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in programs:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# Credit card transfer partners
# ---------------------------------------------------------------------------

TRANSFER_PARTNERS: dict[str, list[str]] = {
    "Chase Ultimate Rewards": [
        "united", "air_canada", "british_airways", "iberia", "singapore",
        "virgin_atlantic", "southwest", "jetblue", "air_france", "ita",
        "emirates",
    ],
    "Amex Membership Rewards": [
        "delta", "air_canada", "british_airways", "cathay", "ana",
        "singapore", "avianca", "air_france", "korean_air", "hawaiian",
        "jetblue", "virgin_atlantic",
    ],
    "Citi ThankYou Points": [
        "turkish", "cathay", "singapore", "avianca", "air_france",
        "jetblue", "qantas", "thai", "eva", "qatar", "etihad",
        "virgin_atlantic",
    ],
    "Capital One Miles": [
        "air_canada", "british_airways", "cathay", "finnair", "air_france",
        "turkish", "avianca", "tap", "qantas",
    ],
    "Bilt Rewards": [
        "united", "american", "air_canada", "turkish", "virgin_atlantic",
        "air_france", "iberia", "alaska", "cathay", "ethiopian",
        "hawaiian",
    ],
}

# Reverse: program → list of credit card partners
_PROGRAM_TRANSFER_SOURCES: dict[str, list[str]] | None = None


def get_transfer_sources(program: str) -> list[str]:
    """Return credit card programs that transfer to this loyalty program."""
    global _PROGRAM_TRANSFER_SOURCES
    if _PROGRAM_TRANSFER_SOURCES is None:
        _PROGRAM_TRANSFER_SOURCES = {}
        for card, programs in TRANSFER_PARTNERS.items():
            for p in programs:
                _PROGRAM_TRANSFER_SOURCES.setdefault(p, []).append(card)
    key = normalize_airline(program)
    return _PROGRAM_TRANSFER_SOURCES.get(key, [])


# ---------------------------------------------------------------------------
# IATA region classification
# ---------------------------------------------------------------------------

# Simplified region zones based on airport IATA code prefixes and known airports
_NORTH_AMERICA_PREFIXES = {"US", "CA", "MX"}  # not used directly, see below

# Known major airports by region (representative, not exhaustive)
_REGION_AIRPORTS: dict[str, set[str]] = {
    "north_america": {
        "SEA", "IAH", "DFW", "LAX", "SFO", "ORD", "JFK", "EWR", "BOS", "ATL",
        "MIA", "DEN", "PHX", "LAS", "MSP", "DTW", "CLT", "PHL", "IAD", "DCA",
        "SAN", "SJC", "PDX", "AUS", "SAT", "HOU", "DAL", "MCO", "TPA", "FLL",
        "BWI", "SLC", "STL", "BNA", "RDU", "IND", "MCI", "CLE", "PIT", "CMH",
        "HNL", "OGG", "ANC",
        "YVR", "YYZ", "YUL", "YOW", "YYC", "YEG", "YWG", "YHZ",
        "MEX", "CUN", "GDL", "SJD", "PVR",
    },
    "europe": {
        "LHR", "LGW", "STN", "CDG", "ORY", "FRA", "MUC", "AMS", "MAD", "BCN",
        "FCO", "MXP", "ZRH", "VIE", "BRU", "LIS", "IST", "SAW", "CPH", "OSL",
        "ARN", "HEL", "WAW", "PRG", "BUD", "DUB", "ATH", "OTP", "SVO", "DME",
        "LED",
    },
    "east_asia": {
        "NRT", "HND", "KIX", "ICN", "GMP", "PEK", "PVG", "HKG", "TPE", "TSA",
        "CTS", "FUK", "NGO", "MNL", "BKK", "DMK", "SIN", "KUL", "CGK", "SGN",
        "HAN", "DEL", "BOM", "BLR", "MAA", "CCU", "DPS", "SUB",
    },
    "oceania": {
        "SYD", "MEL", "BNE", "PER", "AKL", "WLG", "CHC",
    },
    "middle_east": {
        "DXB", "AUH", "DOH", "JED", "RUH", "AMM", "TLV", "BAH",
    },
    "south_america": {
        "GRU", "GIG", "EZE", "SCL", "LIM", "BOG", "PTY", "UIO",
    },
    "africa": {
        "JNB", "CPT", "NBO", "ADD", "CAI", "CMN", "LOS",
    },
}

# Reverse: airport → region
_AIRPORT_REGION: dict[str, str] = {}
for _region, _airports in _REGION_AIRPORTS.items():
    for _apt in _airports:
        _AIRPORT_REGION[_apt] = _region


def get_airport_region(airport: str) -> str:
    """Return the region for an IATA airport code."""
    return _AIRPORT_REGION.get(airport.upper(), "unknown")


def classify_route(origin: str, dest: str) -> str:
    """Classify a route into a region pair for award chart lookup.

    Returns one of:
    - "domestic" (same region, within North America)
    - "transatlantic" (NA ↔ Europe)
    - "transpacific" (NA ↔ East Asia)
    - "intra_asia" (within East Asia)
    - "intra_europe" (within Europe)
    - "europe_asia" (Europe ↔ Asia)
    - "international" (everything else)
    """
    r1 = get_airport_region(origin.upper())
    r2 = get_airport_region(dest.upper())

    if r1 == r2:
        if r1 == "north_america":
            return "domestic"
        if r1 == "east_asia":
            return "intra_asia"
        if r1 == "europe":
            return "intra_europe"
        return "domestic"

    pair = frozenset({r1, r2})
    if pair == {"north_america", "europe"}:
        return "transatlantic"
    if pair == {"north_america", "east_asia"}:
        return "transpacific"
    if pair == {"europe", "east_asia"}:
        return "europe_asia"

    return "international"
