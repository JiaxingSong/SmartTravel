"""Tests for the memory system (sessions, preferences, in-memory store)."""

from __future__ import annotations

import pytest

from smart_travel.memory.session import Message, Session
from smart_travel.memory.preferences import UserPreferences, KNOWN_PREFERENCES
from smart_travel.memory.store import InMemoryMemoryStore


# ---------------------------------------------------------------------------
# Message & Session
# ---------------------------------------------------------------------------

class TestMessage:

    def test_create_message(self):
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.timestamp is not None

    def test_role_preserved(self):
        msg = Message(role="assistant", content="hi")
        assert msg.role == "assistant"


class TestSession:

    def test_create_session(self):
        session = Session(id="test-123")
        assert session.id == "test-123"
        assert len(session.messages) == 0

    def test_add_message(self):
        session = Session(id="test-123")
        msg = Message(role="user", content="hello")
        old_updated = session.updated_at
        session.add_message(msg)
        assert len(session.messages) == 1
        assert session.messages[0] is msg
        assert session.updated_at >= old_updated


# ---------------------------------------------------------------------------
# UserPreferences
# ---------------------------------------------------------------------------

class TestUserPreferences:

    def test_empty_prefs(self):
        prefs = UserPreferences()
        assert not prefs
        assert len(prefs) == 0
        assert prefs.all() == {}

    def test_set_and_get(self):
        prefs = UserPreferences()
        prefs.set("home_city", "Seattle")
        assert prefs.get("home_city") == "Seattle"
        assert len(prefs) == 1

    def test_get_default(self):
        prefs = UserPreferences()
        assert prefs.get("nonexistent", "default") == "default"

    def test_delete(self):
        prefs = UserPreferences({"home_city": "Seattle"})
        prefs.delete("home_city")
        assert prefs.get("home_city") is None
        assert len(prefs) == 0

    def test_all_returns_copy(self):
        data = {"home_city": "Seattle"}
        prefs = UserPreferences(data)
        result = prefs.all()
        result["home_city"] = "London"
        assert prefs.get("home_city") == "Seattle"  # original unchanged

    def test_to_prompt_section_empty(self):
        prefs = UserPreferences()
        assert prefs.to_prompt_section() == ""

    def test_to_prompt_section_with_data(self):
        prefs = UserPreferences({"home_city": "Seattle", "preferred_cabin": "business"})
        section = prefs.to_prompt_section()
        assert "## User preferences" in section
        assert "Seattle" in section
        assert "business" in section

    def test_to_prompt_section_uses_known_labels(self):
        prefs = UserPreferences({"home_city": "Seattle"})
        section = prefs.to_prompt_section()
        assert KNOWN_PREFERENCES["home_city"] in section

    def test_bool_true(self):
        prefs = UserPreferences({"key": "val"})
        assert prefs


# ---------------------------------------------------------------------------
# InMemoryMemoryStore
# ---------------------------------------------------------------------------

class TestInMemoryMemoryStore:

    @pytest.mark.anyio
    async def test_create_session(self):
        store = InMemoryMemoryStore()
        session = await store.create_session()
        assert session.id is not None
        assert len(session.messages) == 0

    @pytest.mark.anyio
    async def test_load_session(self):
        store = InMemoryMemoryStore()
        session = await store.create_session()
        loaded = await store.load_session(session.id)
        assert loaded is not None
        assert loaded.id == session.id

    @pytest.mark.anyio
    async def test_load_session_not_found(self):
        store = InMemoryMemoryStore()
        assert await store.load_session("nonexistent") is None

    @pytest.mark.anyio
    async def test_save_and_load_messages(self):
        store = InMemoryMemoryStore()
        session = await store.create_session()
        await store.save_message(session.id, Message("user", "hello"))
        await store.save_message(session.id, Message("assistant", "hi"))
        loaded = await store.load_session(session.id)
        assert loaded is not None
        assert len(loaded.messages) == 2
        assert loaded.messages[0].role == "user"
        assert loaded.messages[1].role == "assistant"

    @pytest.mark.anyio
    async def test_save_message_nonexistent_session(self):
        store = InMemoryMemoryStore()
        # Should not raise
        await store.save_message("nonexistent", Message("user", "hello"))

    @pytest.mark.anyio
    async def test_list_sessions(self):
        store = InMemoryMemoryStore()
        s1 = await store.create_session()
        s2 = await store.create_session()
        sessions = await store.list_sessions()
        assert len(sessions) == 2
        # Listed sessions should not contain messages
        for s in sessions:
            assert len(s.messages) == 0

    @pytest.mark.anyio
    async def test_list_sessions_limit(self):
        store = InMemoryMemoryStore()
        for _ in range(5):
            await store.create_session()
        sessions = await store.list_sessions(limit=2)
        assert len(sessions) == 2

    @pytest.mark.anyio
    async def test_preferences(self):
        store = InMemoryMemoryStore()
        await store.set_preference("home_city", "Seattle")
        assert await store.get_preference("home_city") == "Seattle"
        assert await store.get_preference("nonexistent") is None

    @pytest.mark.anyio
    async def test_get_all_preferences(self):
        store = InMemoryMemoryStore()
        await store.set_preference("home_city", "Seattle")
        await store.set_preference("preferred_cabin", "business")
        prefs = await store.get_all_preferences()
        assert isinstance(prefs, UserPreferences)
        assert prefs.get("home_city") == "Seattle"
        assert prefs.get("preferred_cabin") == "business"

    @pytest.mark.anyio
    async def test_close_is_noop(self):
        store = InMemoryMemoryStore()
        await store.close()  # should not raise
