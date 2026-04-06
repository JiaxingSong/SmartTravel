"""Unit tests for the airline loyalty account store."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from smart_travel.accounts.store import (
    AccountStore,
    LoyaltyAccount,
    _canonical_airline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path: Path) -> AccountStore:
    return AccountStore(path=tmp_path / "accounts.json", key="")


@pytest.fixture
def store_keyed(tmp_path: Path) -> AccountStore:
    return AccountStore(path=tmp_path / "accounts.json", key="testkey123")


# ---------------------------------------------------------------------------
# LoyaltyAccount
# ---------------------------------------------------------------------------

class TestLoyaltyAccount:
    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        acct = LoyaltyAccount(
            airline="united",
            program_name="MileagePlus",
            email="test@example.com",
            password="secret",
            loyalty_number="UA123",
        )
        d = acct.to_dict()
        restored = LoyaltyAccount.from_dict(d)
        assert restored.airline == acct.airline
        assert restored.email == acct.email
        assert restored.loyalty_number == acct.loyalty_number
        assert restored.account_id == acct.account_id
        assert restored.status == "active"

    def test_defaults_for_missing_fields(self) -> None:
        acct = LoyaltyAccount.from_dict({
            "airline": "delta",
            "program_name": "SkyMiles",
            "email": "a@b.com",
            "password": "x",
            "loyalty_number": "DL1",
        })
        assert acct.locked is False
        assert acct.failed_attempts == 0
        assert acct.status == "active"
        assert acct.account_id  # non-empty UUID generated

    def test_backward_compat_locked_true_maps_to_status(self) -> None:
        """Old records with locked=True but no status field should map to status='locked'."""
        acct = LoyaltyAccount.from_dict({
            "airline": "united", "program_name": "MileagePlus",
            "email": "a@b.com", "password": "x", "loyalty_number": "UA1",
            "locked": True,
        })
        assert acct.status == "locked"

    def test_is_available_property(self) -> None:
        acct = LoyaltyAccount(
            airline="united", program_name="MP", email="a@b.com",
            password="x", loyalty_number="UA1",
        )
        assert acct.is_available is True
        acct.status = "cooling_down"
        assert acct.is_available is False
        acct.status = "locked"
        assert acct.is_available is False


# ---------------------------------------------------------------------------
# AccountStore: basic operations
# ---------------------------------------------------------------------------

class TestAccountStoreBasic:
    def test_starts_empty_if_no_file(self, store: AccountStore) -> None:
        assert store.get_accounts("united") == []

    def test_add_account_persists_to_file(self, tmp_path: Path) -> None:
        path = tmp_path / "accts.json"
        s = AccountStore(path=path, key="")
        s.add_account("united", "user@test.com", "pass123", "UA999")
        assert path.exists()

    def test_add_account_can_be_retrieved(self, store: AccountStore) -> None:
        store.add_account("united", "user@test.com", "pass123", "UA999")
        accounts = store.get_accounts("united")
        assert len(accounts) == 1
        assert accounts[0].email == "user@test.com"
        assert accounts[0].loyalty_number == "UA999"

    def test_add_account_infers_program_name_united(self, store: AccountStore) -> None:
        acct = store.add_account("united", "u@u.com", "pw", "UA1")
        assert acct.program_name == "MileagePlus"

    def test_add_account_infers_program_name_delta(self, store: AccountStore) -> None:
        acct = store.add_account("delta", "d@d.com", "pw", "DL1")
        assert acct.program_name == "SkyMiles"

    def test_add_account_infers_program_name_alaska(self, store: AccountStore) -> None:
        acct = store.add_account("alaska", "a@a.com", "pw", "AS1")
        assert acct.program_name == "Mileage Plan"

    def test_add_account_infers_program_name_aa(self, store: AccountStore) -> None:
        acct = store.add_account("aa", "aa@aa.com", "pw", "AA1")
        assert acct.program_name == "AAdvantage"

    def test_add_account_overwrites_same_email(self, store: AccountStore) -> None:
        store.add_account("united", "same@test.com", "oldpass", "UA1")
        store.add_account("united", "same@test.com", "newpass", "UA2")
        accounts = store.get_accounts("united")
        assert len(accounts) == 1
        assert accounts[0].loyalty_number == "UA2"

    def test_multiple_accounts_per_airline(self, store: AccountStore) -> None:
        store.add_account("united", "user1@test.com", "pw1", "UA1")
        store.add_account("united", "user2@test.com", "pw2", "UA2")
        store.add_account("united", "user3@test.com", "pw3", "UA3")
        assert len(store.get_accounts("united")) == 3

    def test_get_accounts_returns_empty_for_unknown_airline(self, store: AccountStore) -> None:
        assert store.get_accounts("frontier") == []

    def test_get_accounts_excludes_locked(self, store: AccountStore) -> None:
        a1 = store.add_account("united", "locked@t.com", "pw", "UA1")
        store.add_account("united", "active@t.com", "pw", "UA2")
        # Lock after 4 failures (permanent lock threshold)
        for _ in range(4):
            store.mark_cooldown(a1.account_id)
        accounts = store.get_accounts("united")
        assert len(accounts) == 1
        assert accounts[0].email == "active@t.com"

    def test_remove_account(self, store: AccountStore) -> None:
        a = store.add_account("united", "u@u.com", "pw", "UA1")
        assert store.remove_account(a.account_id) is True
        assert store.get_accounts("united") == []

    def test_remove_account_unknown_returns_false(self, store: AccountStore) -> None:
        assert store.remove_account("nonexistent") is False

    def test_list_all_masks_email(self, store: AccountStore) -> None:
        store.add_account("alaska", "myemail@airline.com", "pw", "AS1")
        summary = store.list_all()
        assert "alaska" in summary
        entry = summary["alaska"][0]
        assert "myemail" not in entry["email"]
        assert "@airline.com" in entry["email"]
        assert "pw" not in str(entry)

    def test_list_all_no_password_field(self, store: AccountStore) -> None:
        store.add_account("delta", "d@d.com", "secretpw", "DL1")
        summary = store.list_all()
        entry = summary["delta"][0]
        assert "password" not in entry
        assert "secretpw" not in str(entry)

    def test_list_all_includes_status(self, store: AccountStore) -> None:
        store.add_account("united", "u@u.com", "pw", "UA1")
        entry = store.list_all()["united"][0]
        assert "status" in entry
        assert entry["status"] == "active"


# ---------------------------------------------------------------------------
# AccountStore: pool rotation (get_next_account)
# ---------------------------------------------------------------------------

class TestPoolRotation:
    def test_get_next_account_returns_lru(self, store: AccountStore) -> None:
        a1 = store.add_account("united", "u1@u.com", "pw", "UA1")
        a2 = store.add_account("united", "u2@u.com", "pw", "UA2")
        # Mark a1 as recently used
        store.mark_used(a1.account_id)
        # a2 should be next since it has older last_used (0.0)
        nxt = store.get_next_account("united")
        assert nxt is not None
        assert nxt.account_id == a2.account_id

    def test_get_next_account_rotates_after_use(self, store: AccountStore) -> None:
        a1 = store.add_account("united", "u1@u.com", "pw", "UA1")
        a2 = store.add_account("united", "u2@u.com", "pw", "UA2")

        # First call returns a1 or a2 (both last_used=0.0, either is valid)
        first = store.get_next_account("united")
        assert first is not None
        store.mark_used(first.account_id)

        # Second call returns the OTHER account
        second = store.get_next_account("united")
        assert second is not None
        assert second.account_id != first.account_id

    def test_get_next_account_skips_cooling_down(self, store: AccountStore) -> None:
        a1 = store.add_account("united", "u1@u.com", "pw", "UA1")
        a2 = store.add_account("united", "u2@u.com", "pw", "UA2")
        store.mark_cooldown(a1.account_id, cooldown_secs=9999)
        nxt = store.get_next_account("united")
        assert nxt is not None
        assert nxt.account_id == a2.account_id

    def test_get_next_account_auto_recovers_expired_cooldown(self, store: AccountStore) -> None:
        a1 = store.add_account("united", "u1@u.com", "pw", "UA1")
        # Put in cooldown that already expired
        a1.status = "cooling_down"
        a1.cooldown_until = time.time() - 1  # 1 second ago
        store._save()

        nxt = store.get_next_account("united")
        assert nxt is not None
        assert nxt.account_id == a1.account_id
        assert nxt.status == "active"

    def test_get_next_account_returns_none_when_all_locked(self, store: AccountStore) -> None:
        a1 = store.add_account("united", "u1@u.com", "pw", "UA1")
        # Permanently lock
        for _ in range(4):
            store.mark_cooldown(a1.account_id)
        assert store.get_next_account("united") is None

    def test_get_next_account_returns_none_for_empty_airline(self, store: AccountStore) -> None:
        assert store.get_next_account("frontier") is None


# ---------------------------------------------------------------------------
# AccountStore: cooldown & failure tracking
# ---------------------------------------------------------------------------

class TestCooldownTracking:
    def test_mark_cooldown_sets_cooling_down_status(self, store: AccountStore) -> None:
        acct = store.add_account("united", "u@u.com", "pw", "UA1")
        store.mark_cooldown(acct.account_id)
        accounts = store.get_accounts("united")
        assert accounts[0].status == "cooling_down"
        assert accounts[0].failed_attempts == 1
        assert accounts[0].cooldown_until > time.time()

    def test_mark_cooldown_exponential_backoff(self, store: AccountStore) -> None:
        acct = store.add_account("united", "u@u.com", "pw", "UA1")
        now = time.time()

        # 1st failure: ~1 hour cooldown
        store.mark_cooldown(acct.account_id)
        a = store._find_account(acct.account_id)
        assert a.cooldown_until >= now + 3500  # ~1h
        assert a.status == "cooling_down"

        # Reset for next test
        a.status = "active"
        a.cooldown_until = 0

        # 2nd failure: ~4 hour cooldown
        store.mark_cooldown(acct.account_id)
        assert a.cooldown_until >= now + 14000  # ~4h
        assert a.status == "cooling_down"

        a.status = "active"
        a.cooldown_until = 0

        # 3rd failure: ~24 hour cooldown
        store.mark_cooldown(acct.account_id)
        assert a.cooldown_until >= now + 86000  # ~24h
        assert a.status == "cooling_down"

        a.status = "active"
        a.cooldown_until = 0

        # 4th failure: permanent lock
        store.mark_cooldown(acct.account_id)
        assert a.status == "locked"
        assert a.locked is True

    def test_mark_failed_delegates_to_mark_cooldown(self, store: AccountStore) -> None:
        acct = store.add_account("united", "u@u.com", "pw", "UA1")
        store.mark_failed(acct.account_id)
        a = store._find_account(acct.account_id)
        assert a.failed_attempts == 1
        assert a.status == "cooling_down"

    def test_mark_used_updates_timestamp_and_count(self, store: AccountStore) -> None:
        acct = store.add_account("united", "u@u.com", "pw", "UA1")
        before = time.time()
        store.mark_used(acct.account_id)
        a = store._find_account(acct.account_id)
        assert a.last_used >= before
        assert a.success_count == 1
        assert a.status == "active"

    def test_reset_failures_clears_everything(self, store: AccountStore) -> None:
        acct = store.add_account("united", "u@u.com", "pw", "UA1")
        store.mark_cooldown(acct.account_id)
        store.reset_failures(acct.account_id)
        a = store._find_account(acct.account_id)
        assert a.failed_attempts == 0
        assert a.status == "active"
        assert a.locked is False
        assert a.cooldown_until == 0.0

    def test_mark_failed_noop_for_unknown_id(self, store: AccountStore) -> None:
        store.mark_failed("nonexistent-uuid")  # should not raise


# ---------------------------------------------------------------------------
# AccountStore: pool status
# ---------------------------------------------------------------------------

class TestPoolStatus:
    def test_pool_status_empty(self, store: AccountStore) -> None:
        status = store.get_pool_status("united")
        assert status["total"] == 0
        assert status["active"] == 0

    def test_pool_status_mixed(self, store: AccountStore) -> None:
        a1 = store.add_account("united", "u1@u.com", "pw", "UA1")
        a2 = store.add_account("united", "u2@u.com", "pw", "UA2")
        a3 = store.add_account("united", "u3@u.com", "pw", "UA3")
        store.mark_cooldown(a2.account_id, cooldown_secs=9999)
        for _ in range(4):
            store.mark_cooldown(a3.account_id)
        status = store.get_pool_status("united")
        assert status["total"] == 3
        assert status["active"] == 1
        assert status["cooling_down"] == 1
        assert status["locked"] == 1

    def test_pool_status_next_available(self, store: AccountStore) -> None:
        a1 = store.add_account("united", "u1@u.com", "pw", "UA1")
        store.mark_cooldown(a1.account_id, cooldown_secs=600)
        status = store.get_pool_status("united")
        assert status["active"] == 0
        assert status["next_available"] is not None
        assert status["next_available"] > time.time()


# ---------------------------------------------------------------------------
# AccountStore: obfuscation
# ---------------------------------------------------------------------------

class TestAccountStoreObfuscation:
    def test_plaintext_when_no_key(self, tmp_path: Path) -> None:
        path = tmp_path / "a.json"
        s = AccountStore(path=path, key="")
        s.add_account("united", "u@u.com", "pw", "UA1")
        raw = path.read_bytes()
        parsed = json.loads(raw)
        assert "united" in parsed

    def test_obfuscated_when_key_set(self, tmp_path: Path) -> None:
        path = tmp_path / "a.json"
        s = AccountStore(path=path, key="mykey")
        s.add_account("united", "u@u.com", "pw", "UA1")
        raw = path.read_bytes()
        with pytest.raises(Exception):
            json.loads(raw)

    def test_obfuscation_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "a.json"
        key = "roundtripkey"
        s1 = AccountStore(path=path, key=key)
        s1.add_account("alaska", "a@a.com", "pass", "AS42")
        s2 = AccountStore(path=path, key=key)
        accounts = s2.get_accounts("alaska")
        assert len(accounts) == 1
        assert accounts[0].loyalty_number == "AS42"

    def test_obfuscated_file_differs_from_plaintext(self, tmp_path: Path) -> None:
        plain_path = tmp_path / "plain.json"
        enc_path = tmp_path / "enc.json"
        s_plain = AccountStore(path=plain_path, key="")
        s_plain.add_account("united", "u@u.com", "pw", "UA1")
        s_enc = AccountStore(path=enc_path, key="somekey")
        s_enc.add_account("united", "u@u.com", "pw", "UA1")
        assert plain_path.read_bytes() != enc_path.read_bytes()


# ---------------------------------------------------------------------------
# Alias normalisation
# ---------------------------------------------------------------------------

class TestCanonicalAirline:
    def test_united_airlines_normalises(self) -> None:
        assert _canonical_airline("United Airlines") == "united"

    def test_american_normalises_to_aa(self) -> None:
        assert _canonical_airline("american") == "aa"
        assert _canonical_airline("American Airlines") == "aa"

    def test_delta_variants(self) -> None:
        assert _canonical_airline("Delta Airlines") == "delta"
        assert _canonical_airline("delta air lines") == "delta"

    def test_alaska_variants(self) -> None:
        assert _canonical_airline("Alaska Airlines") == "alaska"

    def test_unknown_passes_through_lowercased(self) -> None:
        assert _canonical_airline("Frontier") == "frontier"
