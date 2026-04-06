"""Unit tests for auto-registration of airline loyalty accounts."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from smart_travel.accounts.registration import (
    generate_credentials,
    register_account,
    ensure_pool_minimum,
    _random_name,
    _random_address,
)


class TestGenerateCredentials:
    def test_email_uses_plus_tag(self) -> None:
        with patch.dict(os.environ, {"POOL_BASE_EMAIL": "user@gmail.com"}):
            email, pw = generate_credentials("united")
            assert email.startswith("user+united_")
            assert email.endswith("@gmail.com")

    def test_email_unique_per_call(self) -> None:
        with patch.dict(os.environ, {"POOL_BASE_EMAIL": "user@gmail.com"}):
            e1, _ = generate_credentials("united")
            e2, _ = generate_credentials("united")
            assert e1 != e2

    def test_password_meets_requirements(self) -> None:
        with patch.dict(os.environ, {"POOL_BASE_EMAIL": "user@gmail.com"}):
            _, pw = generate_credentials("delta")
            assert len(pw) >= 12
            assert any(c.isupper() for c in pw), "Password should have uppercase"
            assert any(c.islower() for c in pw), "Password should have lowercase"
            assert any(c.isdigit() for c in pw), "Password should have digit"

    def test_raises_without_base_email(self) -> None:
        with patch.dict(os.environ, {"POOL_BASE_EMAIL": ""}, clear=False):
            with patch("smart_travel.accounts.email_manager.get_email_manager") as mock_mgr:
                mock_mgr.return_value.email_address = None
                with pytest.raises(ValueError, match="No email available"):
                    generate_credentials("united")


class TestRandomHelpers:
    def test_random_name_returns_two_strings(self) -> None:
        first, last = _random_name()
        assert isinstance(first, str) and len(first) > 0
        assert isinstance(last, str) and len(last) > 0

    def test_random_address_has_required_keys(self) -> None:
        addr = _random_address()
        for key in ("street", "city", "state", "zip"):
            assert key in addr


class TestRegisterAccount:
    @pytest.mark.anyio
    async def test_returns_none_for_unknown_airline(self) -> None:
        result = await register_account("frontier")
        assert result is None

    @pytest.mark.anyio
    async def test_returns_none_without_base_email(self) -> None:
        with patch.dict(os.environ, {"POOL_BASE_EMAIL": ""}, clear=False):
            with patch("smart_travel.accounts.email_manager.get_email_manager") as mock_mgr:
                mock_mgr.return_value.email_address = None
                mock_mgr.return_value.get_or_create_email = AsyncMock(return_value=None)
                result = await register_account("united")
                assert result is None

    @pytest.mark.anyio
    async def test_successful_registration_returns_account(self, tmp_path: Path) -> None:
        """Mock the entire browser flow to verify the wiring."""
        from smart_travel.accounts.store import AccountStore

        mock_store = AccountStore(path=tmp_path / "accts.json", key="")
        mock_fill = AsyncMock(return_value="UA9999999")

        with patch.dict(os.environ, {"POOL_BASE_EMAIL": "test@gmail.com"}):
            with patch("smart_travel.accounts.registration.get_account_store", return_value=mock_store):
                with patch("smart_travel.accounts.registration._FILL_FNS", {"united": mock_fill}):
                    with patch("smart_travel.accounts.registration._register_with_browser") as mock_reg:
                        from smart_travel.accounts.store import LoyaltyAccount
                        mock_reg.return_value = LoyaltyAccount(
                            airline="united", program_name="MileagePlus",
                            email="test+united_abc@gmail.com", password="pw",
                            loyalty_number="UA9999999",
                        )
                        result = await register_account("united")
                        assert result is not None
                        assert result.airline == "united"
                        assert result.loyalty_number == "UA9999999"


class TestEnsurePoolMinimum:
    @pytest.mark.anyio
    async def test_registers_when_below_minimum(self, tmp_path: Path) -> None:
        from smart_travel.accounts.store import AccountStore, LoyaltyAccount

        mock_store = AccountStore(path=tmp_path / "accts.json", key="")
        mock_acct = LoyaltyAccount(
            airline="united", program_name="MileagePlus",
            email="auto@gmail.com", password="pw", loyalty_number="UA111",
        )

        with patch.dict(os.environ, {"POOL_MIN_ACCOUNTS": "2", "POOL_BASE_EMAIL": "x@g.com"}):
            with patch("smart_travel.accounts.registration.get_account_store", return_value=mock_store):
                with patch("smart_travel.accounts.registration.register_account", new=AsyncMock(return_value=mock_acct)):
                    count = await ensure_pool_minimum("united")
                    assert count >= 2

    @pytest.mark.anyio
    async def test_skips_when_pool_full(self, tmp_path: Path) -> None:
        from smart_travel.accounts.store import AccountStore

        mock_store = AccountStore(path=tmp_path / "accts.json", key="")
        mock_store.add_account("united", "u1@u.com", "pw", "UA1")
        mock_store.add_account("united", "u2@u.com", "pw", "UA2")

        with patch.dict(os.environ, {"POOL_MIN_ACCOUNTS": "2"}):
            with patch("smart_travel.accounts.registration.get_account_store", return_value=mock_store):
                with patch("smart_travel.accounts.registration.register_account", new=AsyncMock()) as mock_reg:
                    count = await ensure_pool_minimum("united")
                    mock_reg.assert_not_called()
                    assert count >= 2
