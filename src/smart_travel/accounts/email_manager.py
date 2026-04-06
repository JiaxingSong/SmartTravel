"""Self-managed email account for SmartTravel.

Creates and manages disposable email accounts via the mail.tm REST API.
No browser, no CAPTCHA, fully automated. The agent uses these emails for
airline loyalty program registrations.

The email credentials are persisted to .smart_travel_email.json so the
same inbox is reused across sessions.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EMAIL_STORE_PATH = Path(".smart_travel_email.json")
_MAILTM_BASE = "https://api.mail.tm"


@dataclass
class ManagedEmail:
    """Represents a self-managed email account."""
    address: str
    password: str
    first_name: str = ""
    last_name: str = ""
    domain: str = ""
    token: str = ""
    created_at: float = field(default_factory=time.time)
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ManagedEmail":
        return cls(
            address=d.get("address", ""),
            password=d.get("password", ""),
            first_name=d.get("first_name", ""),
            last_name=d.get("last_name", ""),
            domain=d.get("domain", ""),
            token=d.get("token", ""),
            created_at=d.get("created_at", 0.0),
            verified=d.get("verified", False),
        )


# ---------------------------------------------------------------------------
# mail.tm API helpers
# ---------------------------------------------------------------------------

def _api_request(
    path: str,
    method: str = "GET",
    data: dict | None = None,
    token: str = "",
    timeout: int = 15,
) -> dict:
    """Make an HTTP request to the mail.tm API."""
    url = f"{_MAILTM_BASE}{path}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
        if method == "GET":
            method = "POST"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get_domain() -> str:
    """Fetch the first available mail.tm domain."""
    resp = _api_request("/domains")
    members = resp.get("hydra:member", [])
    if not members:
        raise RuntimeError("No mail.tm domains available")
    return members[0]["domain"]


def _create_account(address: str, password: str) -> dict:
    """Create a mail.tm account."""
    return _api_request("/accounts", data={"address": address, "password": password})


def _get_token(address: str, password: str) -> str:
    """Authenticate and return JWT token."""
    # Token endpoint uses application/json, not ld+json
    url = f"{_MAILTM_BASE}/token"
    body = json.dumps({"address": address, "password": password}).encode()
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["token"]


def _get_messages(token: str) -> list[dict]:
    """Fetch inbox messages."""
    resp = _api_request("/messages", token=token)
    return resp.get("hydra:member", [])


def _get_message(token: str, message_id: str) -> dict:
    """Fetch full message content."""
    return _api_request(f"/messages/{message_id}", token=token)


# ---------------------------------------------------------------------------
# EmailManager
# ---------------------------------------------------------------------------

class EmailManager:
    """Manages a self-owned email account via mail.tm API.

    Persists credentials in a JSON file. If no email exists, creates one
    instantly via API — no browser, no CAPTCHA.
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = store_path or _EMAIL_STORE_PATH
        self._email: ManagedEmail | None = None
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._email = ManagedEmail.from_dict(data)
            except Exception:
                logger.warning("Failed to load email store", exc_info=True)

    def _save(self) -> None:
        if self._email:
            self._path.write_text(json.dumps(self._email.to_dict(), indent=2))

    @property
    def has_email(self) -> bool:
        return self._email is not None and self._email.verified

    @property
    def email_address(self) -> str | None:
        return self._email.address if self._email and self._email.verified else None

    @property
    def email_account(self) -> ManagedEmail | None:
        return self._email

    async def get_or_create_email(self) -> ManagedEmail | None:
        """Return the managed email, creating one if needed. Fully async-safe."""
        if self._email and self._email.verified:
            # Refresh token if we have one
            if not self._email.token:
                try:
                    self._email.token = _get_token(self._email.address, self._email.password)
                    self._save()
                except Exception:
                    logger.debug("Token refresh failed, account may be expired")
            return self._email

        # Create a new email
        try:
            managed = self._create_email()
            if managed:
                self._email = managed
                self._save()
                return managed
        except Exception:
            logger.warning("Email creation failed", exc_info=True)
        return None

    def _create_email(self) -> ManagedEmail | None:
        """Create a new mail.tm email account via API."""
        try:
            domain = _get_domain()
            tag = uuid.uuid4().hex[:8]
            username = f"smarttravelpool{tag}"
            address = f"{username}@{domain}"
            password = f"SmT{uuid.uuid4().hex[:10]}!X"

            logger.info("Creating mail.tm account: %s", address)

            acct = _create_account(address, password)
            actual_addr = acct.get("address", address)

            token = _get_token(actual_addr, password)

            managed = ManagedEmail(
                address=actual_addr,
                password=password,
                domain=domain,
                token=token,
                verified=True,
            )
            logger.info("Email account created: %s", actual_addr)
            return managed

        except Exception:
            logger.warning("mail.tm account creation failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Inbox reading
    # ------------------------------------------------------------------

    def _ensure_token(self) -> str | None:
        """Ensure we have a valid JWT token."""
        if not self._email:
            return None
        if self._email.token:
            return self._email.token
        try:
            self._email.token = _get_token(self._email.address, self._email.password)
            self._save()
            return self._email.token
        except Exception:
            logger.warning("Could not get mail.tm token", exc_info=True)
            return None

    def read_inbox(
        self,
        sender_filter: str = "",
        subject_filter: str = "",
        max_messages: int = 10,
    ) -> list[dict[str, str]]:
        """Read recent emails from the managed inbox.

        Returns list of dicts with keys: id, from, subject, intro, date.
        """
        token = self._ensure_token()
        if not token:
            return []

        try:
            messages = _get_messages(token)
            results = []
            for msg in messages[:max_messages]:
                from_addr = msg.get("from", {}).get("address", "")
                subject = msg.get("subject", "")

                # Apply filters
                if sender_filter and sender_filter.lower() not in from_addr.lower():
                    continue
                if subject_filter and subject_filter.lower() not in subject.lower():
                    continue

                results.append({
                    "id": msg.get("id", ""),
                    "from": from_addr,
                    "subject": subject,
                    "intro": msg.get("intro", ""),
                    "date": msg.get("createdAt", ""),
                })
            return results
        except Exception:
            logger.warning("Failed to read inbox", exc_info=True)
            return []

    def read_message(self, message_id: str) -> dict[str, str] | None:
        """Read full content of a specific message."""
        token = self._ensure_token()
        if not token:
            return None

        try:
            msg = _get_message(token, message_id)
            return {
                "from": msg.get("from", {}).get("address", ""),
                "subject": msg.get("subject", ""),
                "text": msg.get("text", ""),
                "html": msg.get("html", [""])[0] if msg.get("html") else "",
                "date": msg.get("createdAt", ""),
            }
        except Exception:
            logger.warning("Failed to read message %s", message_id, exc_info=True)
            return None

    def extract_verification_link(self, text: str) -> str | None:
        """Extract a verification/confirmation URL from email text."""
        patterns = [
            r'https?://[^\s<>"\']+(?:verify|confirm|activate|validate)[^\s<>"\']*',
            r'https?://[^\s<>"\']+(?:click|action|complete)[^\s<>"\']*',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if m:
                return m.group(0).rstrip(".")
        return None

    def extract_verification_code(self, text: str) -> str | None:
        """Extract a numeric verification code from email text."""
        patterns = [
            r"(?:code|pin|otp|verification)[^0-9]{0,20}(\d{4,8})",
            r"(\d{4,8})\s*(?:is your|verification|code)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if m:
                return m.group(1)
        return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_email_manager: EmailManager | None = None


def get_email_manager() -> EmailManager:
    """Return the shared EmailManager singleton."""
    global _email_manager
    if _email_manager is None:
        _email_manager = EmailManager()
    return _email_manager
