"""Credential persistence layer for airline loyalty accounts.

Accounts are stored as JSON at ACCOUNT_STORE_PATH (default:
.smart_travel_accounts.json). When ACCOUNT_STORE_KEY is set the file bytes
are XOR-obfuscated before writing, preventing casual plaintext reads. This
is NOT cryptographic security — treat the file as sensitive.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROGRAM_NAMES: dict[str, str] = {
    "united": "MileagePlus",
    "alaska": "Mileage Plan",
    "delta": "SkyMiles",
    "aa": "AAdvantage",
    "american": "AAdvantage",
}

_AIRLINE_ALIASES: dict[str, str] = {
    "american": "aa",
    "american airlines": "aa",
    "united airlines": "united",
    "alaska airlines": "alaska",
    "delta air lines": "delta",
    "delta airlines": "delta",
}

# Cooldown durations per failure count (seconds)
_COOLDOWN_SECS: dict[int, float] = {
    1: 3600,       # 1 hour after 1st failure
    2: 14400,      # 4 hours after 2nd
    3: 86400,      # 24 hours after 3rd
}
_PERMANENT_LOCK_THRESHOLD = 4  # lock permanently after this many failures


def _canonical_airline(name: str) -> str:
    """Normalise airline name to lowercase canonical key."""
    key = name.lower().strip()
    return _AIRLINE_ALIASES.get(key, key)


@dataclass
class LoyaltyAccount:
    airline: str
    program_name: str
    email: str
    password: str
    loyalty_number: str
    # Status: "active" | "cooling_down" | "locked"
    status: str = "active"
    failed_attempts: int = 0
    last_used: float = 0.0       # unix timestamp of last successful use
    last_failed: float = 0.0     # unix timestamp of last failure
    cooldown_until: float = 0.0  # unix timestamp when cooling_down expires
    success_count: int = 0
    created_at: float = field(default_factory=time.time)
    account_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Kept for backward compatibility — synced from status
    locked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LoyaltyAccount":
        # Backward compat: if old record only has locked=True, map to status="locked"
        locked = d.get("locked", False)
        status = d.get("status", "locked" if locked else "active")
        return cls(
            airline=d.get("airline", ""),
            program_name=d.get("program_name", ""),
            email=d.get("email", ""),
            password=d.get("password", ""),
            loyalty_number=d.get("loyalty_number", ""),
            status=status,
            failed_attempts=d.get("failed_attempts", 0),
            last_used=d.get("last_used", 0.0),
            last_failed=d.get("last_failed", 0.0),
            cooldown_until=d.get("cooldown_until", 0.0),
            success_count=d.get("success_count", 0),
            created_at=d.get("created_at", 0.0),
            account_id=d.get("account_id", str(uuid.uuid4())),
            locked=locked,
        )

    @property
    def is_available(self) -> bool:
        """True if the account can be used right now."""
        return self.status == "active"


class AccountStore:
    """Persistent JSON store for airline loyalty account credentials.

    Supports a pool of multiple accounts per airline with LRU rotation,
    exponential-backoff cooldowns, and automatic recovery after cooldown expires.

    Thread-safety: not thread-safe. All callers in SmartTravel are async
    and single-threaded within one event loop.
    """

    def __init__(
        self,
        path: Path | None = None,
        key: str | None = None,
    ) -> None:
        if path is None:
            path = Path(os.environ.get("ACCOUNT_STORE_PATH", ".smart_travel_accounts.json"))
        if key is None:
            key = os.environ.get("ACCOUNT_STORE_KEY", "")
        self._path = path
        self._key = key
        self._accounts: dict[str, list[LoyaltyAccount]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Obfuscation
    # ------------------------------------------------------------------

    def _obfuscate(self, data: bytes) -> bytes:
        if not self._key:
            return data
        key_bytes = self._key.encode()
        xored = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
        return base64.b64encode(xored)

    def _deobfuscate(self, data: bytes) -> bytes:
        if not self._key:
            return data
        raw = base64.b64decode(data)
        key_bytes = self._key.encode()
        return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        if not self._key:
            logger.warning(
                "ACCOUNT_STORE_KEY not set — account file is stored as plaintext. "
                "Set this env var to enable obfuscation."
            )
        raw = self._path.read_bytes()
        plaintext = self._deobfuscate(raw)
        data: dict[str, list[dict]] = json.loads(plaintext)
        for airline, entries in data.items():
            self._accounts[airline] = [LoyaltyAccount.from_dict(e) for e in entries]

    def _save(self) -> None:
        data = {
            airline: [acct.to_dict() for acct in accounts]
            for airline, accounts in self._accounts.items()
        }
        plaintext = json.dumps(data, indent=2).encode()
        encoded = self._obfuscate(plaintext)
        self._path.write_bytes(encoded)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auto_recover_cooldowns(self, accounts: list[LoyaltyAccount]) -> None:
        """Recover any cooling_down accounts whose cooldown has expired."""
        now = time.time()
        changed = False
        for a in accounts:
            if a.status == "cooling_down" and now >= a.cooldown_until:
                a.status = "active"
                a.locked = False
                logger.debug("Account %s recovered from cooldown", a.account_id)
                changed = True
        if changed:
            self._save()

    def _find_account(self, account_id: str) -> LoyaltyAccount | None:
        for accounts in self._accounts.values():
            for a in accounts:
                if a.account_id == account_id:
                    return a
        return None

    # ------------------------------------------------------------------
    # Public API — basic CRUD
    # ------------------------------------------------------------------

    def add_account(
        self,
        airline: str,
        email: str,
        password: str,
        loyalty_number: str,
        program_name: str = "",
    ) -> LoyaltyAccount:
        """Add a new account to the pool. Same email replaces existing entry."""
        airline = _canonical_airline(airline)
        if not program_name:
            program_name = _PROGRAM_NAMES.get(airline, airline.title())
        acct = LoyaltyAccount(
            airline=airline,
            program_name=program_name,
            email=email,
            password=password,
            loyalty_number=loyalty_number,
        )
        bucket = self._accounts.setdefault(airline, [])
        bucket[:] = [a for a in bucket if a.email.lower() != email.lower()]
        bucket.append(acct)
        self._save()
        return acct

    def remove_account(self, account_id: str) -> bool:
        """Remove an account from the pool. Returns True if found and removed."""
        for airline, accounts in self._accounts.items():
            for i, a in enumerate(accounts):
                if a.account_id == account_id:
                    accounts.pop(i)
                    self._save()
                    logger.info("Removed account %s from %s pool", account_id, airline)
                    return True
        return False

    def get_accounts(self, airline: str) -> list[LoyaltyAccount]:
        """Return all non-locked accounts (active + cooling_down). Legacy method."""
        airline = _canonical_airline(airline)
        return [a for a in self._accounts.get(airline, []) if a.status != "locked"]

    def list_all(self) -> dict[str, list[dict[str, Any]]]:
        """Return a safe summary of all accounts — passwords never included."""
        result: dict[str, list[dict[str, Any]]] = {}
        for airline, accounts in self._accounts.items():
            result[airline] = [
                {
                    "account_id": a.account_id,
                    "email": a.email[:3] + "***" + a.email[a.email.find("@"):],
                    "loyalty_number": a.loyalty_number,
                    "status": a.status,
                    "locked": a.locked,
                    "failed_attempts": a.failed_attempts,
                    "success_count": a.success_count,
                    "cooldown_until": a.cooldown_until,
                }
                for a in accounts
            ]
        return result

    # ------------------------------------------------------------------
    # Pool selection
    # ------------------------------------------------------------------

    def get_next_account(self, airline: str) -> LoyaltyAccount | None:
        """Return the best available account for the airline using LRU rotation.

        Strategy:
        1. Auto-recover any cooling_down accounts whose cooldown has expired.
        2. Among all active accounts, return the one with the oldest last_used
           (least-recently-used), ensuring fair rotation across the pool.
        3. Returns None only if all accounts are locked.
        """
        airline = _canonical_airline(airline)
        bucket = self._accounts.get(airline, [])
        if not bucket:
            return None

        self._auto_recover_cooldowns(bucket)

        active = [a for a in bucket if a.status == "active"]
        if not active:
            return None

        # LRU: pick the account used least recently
        return min(active, key=lambda a: a.last_used)

    # ------------------------------------------------------------------
    # Pool health tracking
    # ------------------------------------------------------------------

    def mark_used(self, account_id: str) -> None:
        """Record a successful use: update last_used, increment success_count."""
        a = self._find_account(account_id)
        if a:
            a.last_used = time.time()
            a.success_count += 1
            a.status = "active"
            a.locked = False
            self._save()

    def mark_cooldown(self, account_id: str, cooldown_secs: float | None = None) -> None:
        """Put an account into cooldown with exponential backoff.

        Backoff schedule based on failed_attempts BEFORE this call:
          0 failures → 1 hour
          1 failure  → 4 hours
          2 failures → 24 hours
          3+ failures → permanent lock
        """
        a = self._find_account(account_id)
        if not a:
            return
        a.failed_attempts += 1
        a.last_failed = time.time()

        if a.failed_attempts >= _PERMANENT_LOCK_THRESHOLD:
            a.status = "locked"
            a.locked = True
            logger.warning(
                "Account %s permanently locked after %d failures",
                account_id, a.failed_attempts,
            )
        else:
            if cooldown_secs is None:
                cooldown_secs = _COOLDOWN_SECS.get(a.failed_attempts, 3600)
            a.status = "cooling_down"
            a.cooldown_until = time.time() + cooldown_secs
            logger.info(
                "Account %s cooling down for %.0f seconds (failure #%d)",
                account_id, cooldown_secs, a.failed_attempts,
            )
        self._save()

    def mark_failed(self, account_id: str) -> None:
        """Backward-compat wrapper — delegates to mark_cooldown."""
        self.mark_cooldown(account_id)

    def reset_failures(self, account_id: str) -> None:
        """Reset failure tracking after a successful login."""
        a = self._find_account(account_id)
        if a:
            a.failed_attempts = 0
            a.status = "active"
            a.locked = False
            a.cooldown_until = 0.0
            self._save()

    def get_pool_status(self, airline: str) -> dict[str, Any]:
        """Return health summary for an airline's account pool."""
        airline = _canonical_airline(airline)
        bucket = self._accounts.get(airline, [])

        # Recover expired cooldowns before reporting
        self._auto_recover_cooldowns(bucket)

        active = sum(1 for a in bucket if a.status == "active")
        cooling = sum(1 for a in bucket if a.status == "cooling_down")
        locked = sum(1 for a in bucket if a.status == "locked")

        next_available: float | None = None
        if active == 0 and cooling > 0:
            next_available = min(
                a.cooldown_until for a in bucket if a.status == "cooling_down"
            )

        return {
            "airline": airline,
            "total": len(bucket),
            "active": active,
            "cooling_down": cooling,
            "locked": locked,
            "next_available": next_available,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store_instance: AccountStore | None = None


def get_account_store() -> AccountStore:
    """Return the shared AccountStore singleton."""
    global _store_instance
    if _store_instance is None:
        _store_instance = AccountStore()
    return _store_instance
