"""Unit tests for the public award chart data."""
from __future__ import annotations

from smart_travel.data.award_charts import (
    estimate_award_price,
    format_award_estimate,
)


class TestEstimateAwardPrice:
    def test_united_economy_domestic(self) -> None:
        entry = estimate_award_price("united", "economy", 1500)
        assert entry is not None
        assert entry.program == "MileagePlus"
        assert entry.miles_low == 12500
        assert entry.is_dynamic is False

    def test_alaska_economy_domestic(self) -> None:
        entry = estimate_award_price("alaska", "economy", 1500)
        assert entry is not None
        assert entry.program == "Mileage Plan"
        assert entry.miles_low == 7500

    def test_aa_economy_domestic(self) -> None:
        entry = estimate_award_price("aa", "economy", 1500)
        assert entry is not None
        assert entry.program == "AAdvantage"

    def test_delta_is_dynamic(self) -> None:
        entry = estimate_award_price("delta", "economy", 1500)
        assert entry is not None
        assert entry.is_dynamic is True

    def test_short_haul_lower_price(self) -> None:
        short = estimate_award_price("united", "economy", 500)
        long = estimate_award_price("united", "economy", 1500)
        assert short is not None and long is not None
        assert short.miles_low <= long.miles_low

    def test_business_class(self) -> None:
        entry = estimate_award_price("united", "business", 1500)
        assert entry is not None
        assert entry.miles_low > 12500  # more than economy

    def test_unknown_airline_returns_none(self) -> None:
        assert estimate_award_price("frontier", "economy") is None

    def test_american_alias(self) -> None:
        entry = estimate_award_price("american", "economy", 1500)
        assert entry is not None
        assert entry.program == "AAdvantage"


class TestFormatAwardEstimate:
    def test_united_format(self) -> None:
        text = format_award_estimate("united", "MileagePlus", "SEA", "IAH")
        assert "MileagePlus" in text
        assert "12,500" in text

    def test_delta_shows_dynamic(self) -> None:
        text = format_award_estimate("delta", "SkyMiles", "SEA", "IAH")
        assert "dynamic" in text.lower()
