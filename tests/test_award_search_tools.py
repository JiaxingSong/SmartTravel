"""Unit tests for award search tools (no real browser launched)."""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from smart_travel.tools.award_search import (
    AwardResult,
    _is_bot_challenge,
    _normalize_airline,
    _normalize_date,
    _date_to_mmddyyyy,
    _parse_points,
    _parse_taxes,
    _format_results,
    search_awards_tool,
)
from smart_travel.tools.account_tools import add_award_account_tool, list_award_accounts_tool


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

class TestParsePoints:
    def test_comma_separated(self) -> None:
        assert _parse_points("12,500 miles") == 12500

    def test_plain_integer(self) -> None:
        assert _parse_points("30000") == 30000

    def test_with_extra_text(self) -> None:
        assert _parse_points("Award: 15,000 miles") == 15000

    def test_garbage_returns_zero(self) -> None:
        assert _parse_points("N/A") == 0

    def test_empty_returns_zero(self) -> None:
        assert _parse_points("") == 0


class TestParseTaxes:
    def test_dollar_sign(self) -> None:
        assert _parse_taxes("$5.60") == pytest.approx(5.60)

    def test_no_symbol(self) -> None:
        assert _parse_taxes("5.60") == pytest.approx(5.60)

    def test_integer_string(self) -> None:
        assert _parse_taxes("11") == pytest.approx(11.0)

    def test_garbage_returns_zero(self) -> None:
        assert _parse_taxes("free") == 0.0

    def test_empty_returns_zero(self) -> None:
        assert _parse_taxes("") == 0.0


class TestNormalizeAirline:
    def test_united_airlines(self) -> None:
        assert _normalize_airline("United Airlines") == "united"

    def test_alaska_airlines(self) -> None:
        assert _normalize_airline("Alaska Airlines") == "alaska"

    def test_american_airlines(self) -> None:
        assert _normalize_airline("American Airlines") == "aa"
        assert _normalize_airline("aa") == "aa"

    def test_delta_variants(self) -> None:
        assert _normalize_airline("Delta Air Lines") == "delta"
        assert _normalize_airline("Delta Airlines") == "delta"

    def test_unknown_passes_through(self) -> None:
        assert _normalize_airline("Frontier") == "frontier"


class TestNormalizeDate:
    def test_slash_format(self) -> None:
        assert _normalize_date("06/15/2026") == "2026-06-15"

    def test_iso_format_passthrough(self) -> None:
        assert _normalize_date("2026-06-15") == "2026-06-15"

    def test_unparseable_passthrough(self) -> None:
        assert _normalize_date("next friday") == "next friday"


class TestDateToMMDDYYYY:
    def test_converts_iso_to_mmddyyyy(self) -> None:
        assert _date_to_mmddyyyy("2026-06-15") == "06152026"

    def test_unparseable_passthrough(self) -> None:
        result = _date_to_mmddyyyy("bad-date")
        assert result == "bad-date"


class TestIsBotChallenge:
    def test_blocked_url(self) -> None:
        assert _is_bot_challenge("https://example.com/blocked", "") is True

    def test_captcha_text(self) -> None:
        assert _is_bot_challenge("https://example.com", "Please verify you are human") is True

    def test_normal_page(self) -> None:
        assert _is_bot_challenge("https://united.com/results", "Here are your flights") is False


# ---------------------------------------------------------------------------
# AwardResult dataclass
# ---------------------------------------------------------------------------

class TestAwardResult:
    def test_to_dict_contains_all_fields(self) -> None:
        r = AwardResult(
            airline="united", program="MileagePlus",
            origin="SEA", destination="IAH", date="2026-06-15",
            cabin="economy", points=12500, taxes_usd=5.60,
            availability="available", source_url="https://united.com",
        )
        d = r.to_dict()
        assert d["airline"] == "united"
        assert d["points"] == 12500
        assert d["taxes_usd"] == pytest.approx(5.60)
        assert "notes" in d


# ---------------------------------------------------------------------------
# Format results
# ---------------------------------------------------------------------------

class TestFormatResults:
    def test_includes_table_when_results_present(self) -> None:
        results = [
            AwardResult(
                airline="united", program="MileagePlus",
                origin="SEA", destination="IAH", date="2026-06-15",
                cabin="economy", points=12500, taxes_usd=5.60,
                availability="available", source_url="https://united.com",
            )
        ]
        text = _format_results(results, "SEA", "IAH", "2026-06-15", [])
        assert "12,500" in text
        assert "MileagePlus" in text

    def test_shows_skipped_airlines(self) -> None:
        text = _format_results([], "SEA", "IAH", "2026-06-15", ["delta", "alaska"])
        assert "delta" in text.lower() or "Delta" in text
        assert "registration" in text.lower() or "not supported" in text.lower()

    def test_shows_no_availability_message_when_empty(self) -> None:
        text = _format_results([], "SEA", "IAH", "2026-06-15", [])
        assert "No award data" in text


# ---------------------------------------------------------------------------
# search_awards_tool validation
# ---------------------------------------------------------------------------

class TestSearchAwardsTool:
    @pytest.mark.anyio
    async def test_missing_origin_returns_error(self) -> None:
        result = await search_awards_tool.handler(
            {"origin": "", "destination": "IAH", "date": "2026-06-15"}
        )
        assert "required" in result["content"][0]["text"].lower()

    @pytest.mark.anyio
    async def test_missing_destination_returns_error(self) -> None:
        result = await search_awards_tool.handler(
            {"origin": "SEA", "destination": "", "date": "2026-06-15"}
        )
        assert "required" in result["content"][0]["text"].lower()

    @pytest.mark.anyio
    async def test_missing_date_returns_error(self) -> None:
        result = await search_awards_tool.handler(
            {"origin": "SEA", "destination": "IAH", "date": ""}
        )
        assert "required" in result["content"][0]["text"].lower()

    @pytest.mark.anyio
    async def test_date_normalization(self) -> None:
        """Slash-format date should not cause an error."""
        with patch("smart_travel.tools.award_search._find_airlines_for_route", new=AsyncMock(return_value=[])):
            result = await search_awards_tool.handler(
                {"origin": "SEA", "destination": "IAH", "date": "06/15/2026"}
            )
        # Should succeed and mention no availability (no airlines, no accounts)
        assert "content" in result

    @pytest.mark.anyio
    async def test_no_accounts_returns_skipped_note(self) -> None:
        """When no accounts and registration fails, airlines should be listed as failed."""
        with patch(
            "smart_travel.tools.award_search._find_airlines_for_route",
            new=AsyncMock(return_value=["united", "alaska"]),
        ):
            with patch("smart_travel.tools.award_search.get_account_store") as mock_store:
                mock_store.return_value.get_next_account.return_value = None
                with patch("smart_travel.accounts.registration.register_account", new=AsyncMock(return_value=None)):
                    result = await search_awards_tool.handler(
                        {"origin": "SEA", "destination": "IAH", "date": "2026-06-15"}
                    )
        text = result["content"][0]["text"]
        assert "registration" in text.lower() or "not supported" in text.lower()

    @pytest.mark.anyio
    async def test_exception_in_one_airline_does_not_block_others(self) -> None:
        """An exception in one airline scraper should yield an error result, not crash."""
        from smart_travel.accounts.store import LoyaltyAccount

        async def failing_search(*args, **kwargs):
            raise RuntimeError("Simulated scrape failure")

        async def good_search(origin, dest, date, cabin):
            return [AwardResult(
                airline="alaska", program="Mileage Plan",
                origin=origin, destination=dest, date=date, cabin=cabin,
                points=15000, taxes_usd=5.60, availability="available",
                source_url="https://alaskaair.com",
            )]

        mock_account = LoyaltyAccount(
            airline="united", program_name="MileagePlus",
            email="u@u.com", password="pw", loyalty_number="UA1",
        )
        mock_alaska_account = LoyaltyAccount(
            airline="alaska", program_name="Mileage Plan",
            email="a@a.com", password="pw", loyalty_number="AS1",
        )

        def mock_get_accounts(airline):
            if airline == "united":
                return [mock_account]
            if airline == "alaska":
                return [mock_alaska_account]
            return []

        with patch("smart_travel.tools.award_search._find_airlines_for_route",
                   new=AsyncMock(return_value=["united", "alaska"])):
            with patch("smart_travel.tools.award_search.get_account_store") as mock_store:
                mock_store.return_value.get_accounts.side_effect = mock_get_accounts
                with patch.dict("smart_travel.tools.award_search._AIRLINE_SEARCH_FNS", {
                    "united": failing_search,
                    "alaska": good_search,
                }):
                    result = await search_awards_tool.handler(
                        {"origin": "SEA", "destination": "IAH", "date": "2026-06-15"}
                    )

        text = result["content"][0]["text"]
        # Alaska results should be present
        assert "15,000" in text or "Mileage Plan" in text


# ---------------------------------------------------------------------------
# Account tools
# ---------------------------------------------------------------------------

class TestAddAwardAccountTool:
    @pytest.mark.anyio
    async def test_success_does_not_echo_password(self, tmp_path: Path) -> None:
        from smart_travel.accounts.store import AccountStore
        store = AccountStore(path=tmp_path / "a.json", key="")
        with patch("smart_travel.tools.account_tools.get_account_store", return_value=store):
            result = await add_award_account_tool.handler({
                "airline": "united",
                "email": "user@test.com",
                "password": "supersecret",
                "loyalty_number": "UA123",
            })
        text = result["content"][0]["text"]
        assert "supersecret" not in text
        assert "MileagePlus" in text
        assert "UA123" in text

    @pytest.mark.anyio
    async def test_missing_airline_returns_error(self) -> None:
        result = await add_award_account_tool.handler({
            "airline": "", "email": "u@u.com", "password": "pw", "loyalty_number": "1"
        })
        assert "required" in result["content"][0]["text"].lower()

    @pytest.mark.anyio
    async def test_missing_email_returns_error(self) -> None:
        result = await add_award_account_tool.handler({
            "airline": "united", "email": "", "password": "pw", "loyalty_number": "1"
        })
        assert "required" in result["content"][0]["text"].lower()


class TestListAwardAccountsTool:
    @pytest.mark.anyio
    async def test_empty_store_returns_guidance(self, tmp_path: Path) -> None:
        from smart_travel.accounts.store import AccountStore
        store = AccountStore(path=tmp_path / "a.json", key="")
        with patch("smart_travel.tools.account_tools.get_account_store", return_value=store):
            result = await list_award_accounts_tool.handler({})
        text = result["content"][0]["text"]
        assert "No award accounts" in text or "add_award_account" in text

    @pytest.mark.anyio
    async def test_shows_accounts_without_password(self, tmp_path: Path) -> None:
        from smart_travel.accounts.store import AccountStore
        store = AccountStore(path=tmp_path / "a.json", key="")
        store.add_account("united", "user@test.com", "mysecret", "UA999")
        with patch("smart_travel.tools.account_tools.get_account_store", return_value=store):
            result = await list_award_accounts_tool.handler({})
        text = result["content"][0]["text"]
        assert "mysecret" not in text
        assert "UA999" in text
        assert "united" in text.lower() or "United" in text
