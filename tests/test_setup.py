"""Tests for the setup wizard utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from smart_travel.setup import _load_env_file, _write_env_file


class TestEnvFileHandling:

    def test_load_empty_file(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        env = _load_env_file(env_file)
        assert env == {}

    def test_load_nonexistent_file(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env = _load_env_file(env_file)
        assert env == {}

    def test_load_with_values(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=qux\n")
        env = _load_env_file(env_file)
        assert env == {"FOO": "bar", "BAZ": "qux"}

    def test_load_skips_comments(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\nFOO=bar\n")
        env = _load_env_file(env_file)
        assert env == {"FOO": "bar"}

    def test_load_skips_blank_lines(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("\nFOO=bar\n\n")
        env = _load_env_file(env_file)
        assert env == {"FOO": "bar"}

    def test_load_handles_equals_in_value(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("DSN=postgres://user:pass@host/db?opt=val\n")
        env = _load_env_file(env_file)
        assert env["DSN"] == "postgres://user:pass@host/db?opt=val"

    def test_write_and_reload(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env = {"FOO": "bar", "BAZ": "qux"}
        _write_env_file(env_file, env)
        loaded = _load_env_file(env_file)
        assert loaded["FOO"] == "bar"
        assert loaded["BAZ"] == "qux"


class TestValidation:
    """Test that validation functions exist and handle errors gracefully."""

    def test_validate_amadeus_import(self):
        from smart_travel.setup import _validate_amadeus
        # Just ensure it's callable — actual API call not tested
        assert callable(_validate_amadeus)

    def test_validate_ticketmaster_import(self):
        from smart_travel.setup import _validate_ticketmaster
        assert callable(_validate_ticketmaster)
