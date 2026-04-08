"""Tests for the global award chart database and M*N generator."""
from __future__ import annotations

from smart_travel.data.award_charts import (
    PROGRAMS,
    get_redemption_options,
    compute_cents_per_mile,
    RedemptionOption,
)
from smart_travel.data.alliances import (
    classify_route,
    get_alliance,
    get_alliance_partners,
    get_bookable_programs,
    get_transfer_sources,
    normalize_airline,
    AIRLINE_ALLIANCE,
)


# ---------------------------------------------------------------------------
# Alliance data
# ---------------------------------------------------------------------------

class TestAlliances:
    def test_united_is_star_alliance(self) -> None:
        assert get_alliance("united") == "star_alliance"

    def test_american_is_oneworld(self) -> None:
        assert get_alliance("american") == "oneworld"

    def test_delta_is_skyteam(self) -> None:
        assert get_alliance("delta") == "skyteam"

    def test_southwest_is_independent(self) -> None:
        assert get_alliance("southwest") == "independent"

    def test_ana_is_star_alliance(self) -> None:
        assert get_alliance("ana") == "star_alliance"

    def test_british_airways_is_oneworld(self) -> None:
        assert get_alliance("british_airways") == "oneworld"

    def test_alliance_partners_excludes_self(self) -> None:
        partners = get_alliance_partners("united")
        assert "united" not in partners
        assert "ana" in partners
        assert "lufthansa" in partners

    def test_independent_has_no_partners(self) -> None:
        assert get_alliance_partners("southwest") == []


class TestNormalizeAirline:
    def test_iata_code(self) -> None:
        assert normalize_airline("UA") == "united"
        assert normalize_airline("BA") == "british_airways"
        assert normalize_airline("NH") == "ana"

    def test_display_name(self) -> None:
        assert normalize_airline("United Airlines") == "united"
        assert normalize_airline("British Airways") == "british_airways"
        assert normalize_airline("Cathay Pacific") == "cathay"

    def test_canonical_key(self) -> None:
        assert normalize_airline("united") == "united"


class TestClassifyRoute:
    def test_domestic(self) -> None:
        assert classify_route("SEA", "IAH") == "domestic"
        assert classify_route("JFK", "LAX") == "domestic"

    def test_transatlantic(self) -> None:
        assert classify_route("JFK", "LHR") == "transatlantic"
        assert classify_route("ORD", "CDG") == "transatlantic"

    def test_transpacific(self) -> None:
        assert classify_route("LAX", "NRT") == "transpacific"
        assert classify_route("SEA", "ICN") == "transpacific"

    def test_intra_europe(self) -> None:
        assert classify_route("LHR", "CDG") == "intra_europe"

    def test_intra_asia(self) -> None:
        assert classify_route("NRT", "SIN") == "intra_asia"
        assert classify_route("HKG", "BKK") == "intra_asia"


class TestBookablePrograms:
    def test_united_flight_bookable_by_star_alliance(self) -> None:
        programs = get_bookable_programs("united")
        assert "united" in programs
        assert "ana" in programs          # Star Alliance
        assert "lufthansa" in programs    # Star Alliance
        assert "air_canada" in programs   # Star Alliance
        assert "delta" not in programs    # SkyTeam — can't book United

    def test_american_bookable_by_oneworld(self) -> None:
        programs = get_bookable_programs("american")
        assert "british_airways" in programs
        assert "cathay" in programs
        assert "united" not in programs

    def test_alaska_special_partners(self) -> None:
        # Alaska has special partners outside oneworld
        programs = get_bookable_programs("jal")
        assert "jal" in programs
        # Alaska can book JAL (special partner)
        assert "alaska" in programs


class TestTransferSources:
    def test_united_transfer_partners(self) -> None:
        sources = get_transfer_sources("united")
        assert "Chase Ultimate Rewards" in sources
        assert "Bilt Rewards" in sources

    def test_delta_transfer_partners(self) -> None:
        sources = get_transfer_sources("delta")
        assert "Amex Membership Rewards" in sources

    def test_turkish_transfer_partners(self) -> None:
        sources = get_transfer_sources("turkish")
        assert "Citi ThankYou Points" in sources
        assert "Capital One Miles" in sources


# ---------------------------------------------------------------------------
# Award charts
# ---------------------------------------------------------------------------

class TestProgramCoverage:
    def test_at_least_26_programs(self) -> None:
        assert len(PROGRAMS) >= 26

    def test_all_major_na_programs(self) -> None:
        for key in ["united", "delta", "american", "alaska", "air_canada"]:
            assert key in PROGRAMS, f"Missing NA program: {key}"

    def test_all_major_asia_programs(self) -> None:
        for key in ["ana", "jal", "cathay", "singapore", "korean_air"]:
            assert key in PROGRAMS, f"Missing Asia program: {key}"

    def test_all_major_europe_programs(self) -> None:
        for key in ["british_airways", "lufthansa", "air_france", "turkish"]:
            assert key in PROGRAMS, f"Missing Europe program: {key}"


class TestChartRates:
    def test_united_domestic_economy(self) -> None:
        rate = PROGRAMS["united"].get_rate("domestic", "economy")
        assert rate is not None
        assert rate.miles_low == 12500

    def test_ana_transpacific_first(self) -> None:
        rate = PROGRAMS["ana"].get_rate("transpacific", "first")
        assert rate is not None
        assert rate.miles_low == 105000

    def test_delta_is_dynamic(self) -> None:
        rate = PROGRAMS["delta"].get_rate("domestic", "economy")
        assert rate is not None
        assert rate.is_dynamic is True

    def test_ba_short_haul_avios(self) -> None:
        rate = PROGRAMS["british_airways"].get_rate("intra_europe", "economy")
        assert rate is not None
        assert rate.miles_low <= 10000  # famous sweet spot

    def test_turkish_transatlantic_business(self) -> None:
        rate = PROGRAMS["turkish"].get_rate("transatlantic", "business")
        assert rate is not None
        assert rate.miles_low == 45000  # excellent value

    def test_fallback_to_international(self) -> None:
        """If route_region not found, should fall back to 'international'."""
        rate = PROGRAMS["united"].get_rate("some_unknown_region", "economy")
        assert rate is not None  # should get international rate


# ---------------------------------------------------------------------------
# M×N generator
# ---------------------------------------------------------------------------

class TestRedemptionOptions:
    def test_united_flight_domestic_returns_multiple_programs(self) -> None:
        options = get_redemption_options("united", "economy", "domestic", cash_price_usd=224)
        assert len(options) >= 5  # United + Star Alliance partners
        # Own metal should be present
        own = [o for o in options if o.booking_type == "own_metal"]
        assert len(own) == 1
        assert own[0].program_name == "MileagePlus"

    def test_options_sorted_by_miles(self) -> None:
        options = get_redemption_options("united", "economy", "domestic")
        miles = [o.miles_required for o in options]
        assert miles == sorted(miles)

    def test_cents_per_mile_calculated(self) -> None:
        options = get_redemption_options("united", "economy", "domestic", cash_price_usd=224)
        for o in options:
            if o.miles_required > 0:
                assert o.cents_per_mile > 0

    def test_transfer_partners_populated(self) -> None:
        options = get_redemption_options("united", "economy", "domestic")
        united_option = [o for o in options if o.program_airline == "united"][0]
        assert "Chase Ultimate Rewards" in united_option.transfer_partners

    def test_transpacific_includes_asian_programs(self) -> None:
        options = get_redemption_options("ana", "business", "transpacific", cash_price_usd=3000)
        program_names = [o.program_name for o in options]
        assert "ANA Mileage Club" in program_names  # own metal
        assert "MileagePlus" in program_names        # Star Alliance
        assert "Aeroplan" in program_names            # Star Alliance

    def test_oneworld_flight_gets_oneworld_programs(self) -> None:
        options = get_redemption_options("british_airways", "economy", "transatlantic")
        program_airlines = [o.program_airline for o in options]
        assert "american" in program_airlines    # oneworld
        assert "cathay" in program_airlines      # oneworld
        assert "united" not in program_airlines  # Star Alliance — shouldn't be here


class TestComputeCPM:
    def test_basic_calculation(self) -> None:
        assert compute_cents_per_mile(224, 12500) == 1.79

    def test_zero_miles(self) -> None:
        assert compute_cents_per_mile(100, 0) == 0.0

    def test_high_value(self) -> None:
        cpp = compute_cents_per_mile(5000, 75000)
        assert 6.0 < cpp < 7.0
