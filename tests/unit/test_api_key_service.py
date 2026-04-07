"""Tests for the API key resolution logic."""

from unittest.mock import MagicMock, patch

import pytest

from app.auth.encryption import encrypt_api_key
from app.services.api_key_service import resolve_api_key


def _make_user(role="user", encrypted_api_key=None, free_runs_used=0):
    user = MagicMock()
    user.role = role
    user.encrypted_api_key = encrypted_api_key
    user.free_runs_used = free_runs_used
    return user


class TestResolveApiKey:
    """Tests for the resolve_api_key function which determines which API key to use for a user."""

    def test_admin_always_gets_global_key(self):
        user = _make_user(role="admin", free_runs_used=100)
        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.api_key = "sk-global-key"
            mock_settings.free_run_limit = 1
            assert resolve_api_key(user) == "sk-global-key"

    def test_user_with_own_key_uses_own_key(self):
        encrypted = encrypt_api_key("sk-user-own-key")
        user = _make_user(encrypted_api_key=encrypted, free_runs_used=5)
        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.free_run_limit = 1
            assert resolve_api_key(user) == "sk-user-own-key"

    def test_user_within_free_limit_gets_global_key(self):
        user = _make_user(free_runs_used=0)
        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.api_key = "sk-global-key"
            mock_settings.free_run_limit = 1
            assert resolve_api_key(user) == "sk-global-key"

    def test_user_exceeded_free_limit_no_key_raises(self):
        user = _make_user(free_runs_used=1)
        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.free_run_limit = 1
            with pytest.raises(ValueError, match="Free trial exhausted"):
                resolve_api_key(user)

    def test_admin_raises_if_no_global_key(self):
        user = _make_user(role="admin")
        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.api_key = ""
            with pytest.raises(ValueError, match="Server API key is not configured"):
                resolve_api_key(user)

    def test_free_trial_raises_if_no_global_key(self):
        user = _make_user(free_runs_used=0)
        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.api_key = ""
            mock_settings.free_run_limit = 1
            with pytest.raises(ValueError, match="Server API key is not configured"):
                resolve_api_key(user)

    def test_configurable_free_run_limit(self):
        user = _make_user(free_runs_used=2)
        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.api_key = "sk-global"
            mock_settings.free_run_limit = 3
            assert resolve_api_key(user) == "sk-global"
