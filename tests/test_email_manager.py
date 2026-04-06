"""Unit tests for the email manager (mail.tm API based, no real HTTP calls)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from smart_travel.accounts.email_manager import (
    EmailManager,
    ManagedEmail,
)


@pytest.fixture
def mgr(tmp_path: Path) -> EmailManager:
    return EmailManager(store_path=tmp_path / "email.json")


class TestManagedEmail:
    def test_to_dict_roundtrip(self) -> None:
        email = ManagedEmail(
            address="test@example.com",
            password="pw123",
            domain="example.com",
            token="jwt_token",
            verified=True,
        )
        d = email.to_dict()
        restored = ManagedEmail.from_dict(d)
        assert restored.address == email.address
        assert restored.password == email.password
        assert restored.verified is True
        assert restored.domain == "example.com"

    def test_defaults(self) -> None:
        email = ManagedEmail.from_dict({"address": "x@y.com", "password": "p"})
        assert email.verified is False
        assert email.domain == ""
        assert email.token == ""


class TestEmailManager:
    def test_starts_without_email(self, mgr: EmailManager) -> None:
        assert mgr.has_email is False
        assert mgr.email_address is None

    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "email.json"
        mgr1 = EmailManager(store_path=path)
        mgr1._email = ManagedEmail(
            address="test@deltajohnsons.com",
            password="pw",
            domain="deltajohnsons.com",
            token="tok123",
            verified=True,
        )
        mgr1._save()

        mgr2 = EmailManager(store_path=path)
        assert mgr2.has_email is True
        assert mgr2.email_address == "test@deltajohnsons.com"
        assert mgr2.email_account.verified is True

    def test_has_email_false_when_not_verified(self, tmp_path: Path) -> None:
        path = tmp_path / "email.json"
        mgr = EmailManager(store_path=path)
        mgr._email = ManagedEmail(address="x@y.com", password="pw", verified=False)
        assert mgr.has_email is False
        assert mgr.email_address is None


class TestExtractVerification:
    def test_extract_verification_link(self, mgr: EmailManager) -> None:
        body = "Click here to verify: https://example.com/verify?token=abc123 end"
        link = mgr.extract_verification_link(body)
        assert link is not None
        assert "verify" in link

    def test_extract_verification_code(self, mgr: EmailManager) -> None:
        body = "Your verification code is: 483921. Enter this code to continue."
        code = mgr.extract_verification_code(body)
        assert code == "483921"

    def test_extract_code_returns_none_when_absent(self, mgr: EmailManager) -> None:
        body = "Welcome to our service! No codes here."
        assert mgr.extract_verification_code(body) is None

    def test_extract_link_returns_none_when_absent(self, mgr: EmailManager) -> None:
        body = "Just a plain email with no links."
        assert mgr.extract_verification_link(body) is None


class TestGetOrCreateEmail:
    @pytest.mark.anyio
    async def test_returns_existing_verified(self, mgr: EmailManager) -> None:
        mgr._email = ManagedEmail(
            address="existing@example.com", password="pw",
            domain="example.com", token="tok", verified=True,
        )
        result = await mgr.get_or_create_email()
        assert result is not None
        assert result.address == "existing@example.com"

    @pytest.mark.anyio
    async def test_creates_new_when_none(self, mgr: EmailManager) -> None:
        mock_email = ManagedEmail(
            address="new@example.com", password="pw",
            domain="example.com", token="tok", verified=True,
        )
        with patch.object(mgr, "_create_email", return_value=mock_email):
            result = await mgr.get_or_create_email()
        assert result is not None
        assert result.address == "new@example.com"

    @pytest.mark.anyio
    async def test_returns_none_on_creation_failure(self, mgr: EmailManager) -> None:
        with patch.object(mgr, "_create_email", return_value=None):
            result = await mgr.get_or_create_email()
        assert result is None

    @pytest.mark.anyio
    async def test_saves_after_creation(self, mgr: EmailManager) -> None:
        mock_email = ManagedEmail(
            address="saved@example.com", password="pw",
            domain="example.com", token="tok", verified=True,
        )
        with patch.object(mgr, "_create_email", return_value=mock_email):
            await mgr.get_or_create_email()
        assert mgr._path.exists()
        data = json.loads(mgr._path.read_text())
        assert data["address"] == "saved@example.com"


class TestReadInbox:
    def test_returns_empty_without_email(self, mgr: EmailManager) -> None:
        assert mgr.read_inbox() == []

    def test_returns_empty_without_verified(self, mgr: EmailManager) -> None:
        mgr._email = ManagedEmail(address="x@y.com", password="pw", verified=False)
        assert mgr.read_inbox() == []

    def test_reads_messages_with_filter(self, mgr: EmailManager) -> None:
        mgr._email = ManagedEmail(
            address="x@y.com", password="pw", token="tok", verified=True,
        )
        mock_messages = [
            {"id": "1", "from": {"address": "airline@united.com"}, "subject": "Confirm", "intro": "Click here", "createdAt": "2026-04-06"},
            {"id": "2", "from": {"address": "other@spam.com"}, "subject": "Buy now", "intro": "Deal", "createdAt": "2026-04-06"},
        ]
        with patch("smart_travel.accounts.email_manager._get_messages", return_value=mock_messages):
            results = mgr.read_inbox(sender_filter="united")
        assert len(results) == 1
        assert results[0]["from"] == "airline@united.com"
