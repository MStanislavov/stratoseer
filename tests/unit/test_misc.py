"""Unit tests for miscellaneous modules: prompt_loader, search_tool, url_fetch_tool,
auth dependencies, email, oauth, and main.py helpers."""

import asyncio
import smtplib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# PromptLoader
# ---------------------------------------------------------------------------


class TestPromptLoader:
    """Tests for app.llm.prompt_loader.PromptLoader."""

    def test_load_existing_file(self, tmp_path: Path):
        from app.llm.prompt_loader import PromptLoader

        prompt_file = tmp_path / "greeting.md"
        prompt_file.write_text("Hello, {name}!", encoding="utf-8")

        loader = PromptLoader(prompts_dir=tmp_path)
        result = loader.load("greeting", name="World")
        assert result == "Hello, World!"

    def test_load_missing_file_returns_fallback(self, tmp_path: Path):
        from app.llm.prompt_loader import PromptLoader

        loader = PromptLoader(prompts_dir=tmp_path)
        result = loader.load("nonexistent")
        assert result == "You are a helpful nonexistent agent."

    def test_load_caches_template(self, tmp_path: Path):
        from app.llm.prompt_loader import PromptLoader

        prompt_file = tmp_path / "cached.md"
        prompt_file.write_text("Version 1", encoding="utf-8")

        loader = PromptLoader(prompts_dir=tmp_path)
        assert loader.load("cached") == "Version 1"

        # Overwrite file -- cached value should still be returned
        prompt_file.write_text("Version 2", encoding="utf-8")
        assert loader.load("cached") == "Version 1"

    def test_clear_cache_forces_reload(self, tmp_path: Path):
        from app.llm.prompt_loader import PromptLoader

        prompt_file = tmp_path / "mutable.md"
        prompt_file.write_text("Original", encoding="utf-8")

        loader = PromptLoader(prompts_dir=tmp_path)
        assert loader.load("mutable") == "Original"

        prompt_file.write_text("Updated", encoding="utf-8")
        loader.clear_cache()
        assert loader.load("mutable") == "Updated"

    def test_load_without_kwargs_returns_raw_template(self, tmp_path: Path):
        from app.llm.prompt_loader import PromptLoader

        prompt_file = tmp_path / "raw.md"
        prompt_file.write_text("No placeholders here.", encoding="utf-8")

        loader = PromptLoader(prompts_dir=tmp_path)
        assert loader.load("raw") == "No placeholders here."

    def test_load_with_missing_template_var(self, tmp_path: Path):
        from app.llm.prompt_loader import PromptLoader

        prompt_file = tmp_path / "partial.md"
        prompt_file.write_text("Hello {name}, your role is {role}.", encoding="utf-8")

        loader = PromptLoader(prompts_dir=tmp_path)
        # Missing 'role' var -- should return raw template
        result = loader.load("partial", name="Alice")
        assert result == "Hello {name}, your role is {role}."

    def test_load_missing_file_is_not_cached(self, tmp_path: Path):
        """A missing prompt file should not pollute the cache."""
        from app.llm.prompt_loader import PromptLoader

        loader = PromptLoader(prompts_dir=tmp_path)
        result = loader.load("ghost")
        assert "ghost" in result

        # Now create the file -- should pick it up since it was never cached
        (tmp_path / "ghost.md").write_text("I exist now!", encoding="utf-8")
        assert loader.load("ghost") == "I exist now!"


# ---------------------------------------------------------------------------
# SafeDuckDuckGoSearchTool
# ---------------------------------------------------------------------------


class TestSafeDuckDuckGoSearchTool:
    """Tests for app.llm.search_tool.SafeDuckDuckGoSearchTool.

    DDGS is imported locally inside _run(), so we patch 'ddgs.DDGS'.
    """

    def _make_tool(self, *, timelimit="", max_results=10, backend="google"):
        """Build a SafeDuckDuckGoSearchTool bypassing the model_validator that imports ddgs.engines."""
        from app.llm.search_tool import SafeDuckDuckGoSearchTool

        tool = SafeDuckDuckGoSearchTool.model_construct(
            name="duckduckgo_search",
            description="Search",
            max_results=max_results,
            region="wt-wt",
            timelimit=timelimit,
        )
        tool._backend = backend
        return tool

    @patch("ddgs.DDGS")
    def test_run_returns_formatted_results(self, mock_ddgs_cls):
        """_run should format results from DDGS."""
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.text.return_value = [
            {"title": "Result 1", "href": "https://example.com/1", "body": "Snippet 1"},
            {"title": "Result 2", "href": "https://example.com/2", "body": "Snippet 2"},
        ]
        mock_ddgs_cls.return_value = mock_instance

        tool = self._make_tool(backend="google,duckduckgo")
        result = tool._run("test query")
        assert "Result 1" in result
        assert "Result 2" in result
        assert "https://example.com/1" in result

    @patch("ddgs.DDGS")
    def test_run_no_results(self, mock_ddgs_cls):
        """_run should return a message when no results are found."""
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.text.return_value = []
        mock_ddgs_cls.return_value = mock_instance

        tool = self._make_tool()
        result = tool._run("obscure query")
        assert "No good DuckDuckGo Search Result was found" in result

    @patch("ddgs.DDGS")
    def test_run_handles_exception(self, mock_ddgs_cls):
        """_run should catch exceptions and return an error message."""
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.text.side_effect = RuntimeError("Network down")
        mock_ddgs_cls.return_value = mock_instance

        tool = self._make_tool()
        result = tool._run("fail query")
        assert "Search error:" in result
        assert "Network down" in result

    @patch("ddgs.DDGS")
    def test_run_with_timelimit(self, mock_ddgs_cls):
        """_run should pass timelimit when set."""
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.text.return_value = [
            {"title": "Recent", "href": "https://ex.com", "body": "Fresh"},
        ]
        mock_ddgs_cls.return_value = mock_instance

        tool = self._make_tool(timelimit="w", max_results=5)
        result = tool._run("weekly news")
        assert "Recent" in result
        call_kwargs = mock_instance.text.call_args
        assert call_kwargs[1]["timelimit"] == "w"

    async def test_arun_delegates_to_run(self):
        """_arun should delegate to _run via asyncio.to_thread."""
        tool = self._make_tool()
        tool._run = MagicMock(return_value="mocked result")

        result = await tool._arun("async query")
        assert result == "mocked result"
        tool._run.assert_called_once_with("async query")

    def test_resolve_backends_filters_blocked(self):
        """_resolve_backends should exclude blocked engines."""
        mock_engines_mod = MagicMock()
        mock_engines_mod.ENGINES = {
            "text": {
                "google": {},
                "duckduckgo": {},
                "wikipedia": {},
                "grokipedia": {},
                "brave": {},
            }
        }
        with patch.dict("sys.modules", {"ddgs.engines": mock_engines_mod}):
            from importlib import reload
            import app.llm.search_tool as st
            reload(st)

            tool = st.SafeDuckDuckGoSearchTool.model_construct(
                name="duckduckgo_search",
                description="Search",
                max_results=10,
                region="wt-wt",
                timelimit="",
            )
            tool._backend = ""

            result = st.SafeDuckDuckGoSearchTool._resolve_backends(tool)
            assert "wikipedia" not in result._backend
            assert "grokipedia" not in result._backend
            assert "google" in result._backend


# ---------------------------------------------------------------------------
# URLFetchTool
# ---------------------------------------------------------------------------


class TestURLFetchTool:
    """Tests for app.llm.url_fetch_tool.URLFetchTool."""

    @patch("app.llm.url_fetch_tool.httpx.Client")
    def test_run_returns_parsed_html(self, mock_client_cls):
        from app.llm.url_fetch_tool import URLFetchTool

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><p>Hello World</p><script>var x=1;</script></body></html>"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        tool = URLFetchTool()
        result = tool._run("https://example.com")
        assert "HTTP 200" in result
        assert "Hello World" in result
        # Script content should be stripped
        assert "var x=1" not in result

    @patch("app.llm.url_fetch_tool.httpx.Client")
    def test_run_strips_style_tags(self, mock_client_cls):
        from app.llm.url_fetch_tool import URLFetchTool

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><head><style>body{color:red}</style></head><body><p>Content</p></body></html>"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        tool = URLFetchTool()
        result = tool._run("https://example.com")
        assert "Content" in result
        assert "color:red" not in result

    @patch("app.llm.url_fetch_tool.httpx.Client")
    def test_run_connection_error(self, mock_client_cls):
        from app.llm.url_fetch_tool import URLFetchTool

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = ConnectionError("Connection refused")
        mock_client_cls.return_value = mock_client

        tool = URLFetchTool()
        result = tool._run("https://unreachable.test")
        assert "Fetch error:" in result

    @patch("app.llm.url_fetch_tool.httpx.Client")
    def test_run_timeout_error(self, mock_client_cls):
        import httpx as _httpx
        from app.llm.url_fetch_tool import URLFetchTool

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = _httpx.TimeoutException("Request timed out")
        mock_client_cls.return_value = mock_client

        tool = URLFetchTool()
        result = tool._run("https://slow.test")
        assert "Fetch error:" in result

    @patch("app.llm.url_fetch_tool.httpx.Client")
    def test_run_truncates_long_content(self, mock_client_cls):
        from app.llm.url_fetch_tool import URLFetchTool, _MAX_BODY_CHARS

        long_text = "A" * (_MAX_BODY_CHARS + 5000)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = f"<html><body><p>{long_text}</p></body></html>"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        tool = URLFetchTool()
        result = tool._run("https://example.com/long")
        # "HTTP 200\n\n" prefix + body should not exceed the limit meaningfully
        body_part = result.split("\n\n", 1)[1]
        assert len(body_part) <= _MAX_BODY_CHARS

    @patch("app.llm.url_fetch_tool.httpx.Client")
    async def test_arun_delegates_to_run(self, mock_client_cls):
        from app.llm.url_fetch_tool import URLFetchTool

        tool = URLFetchTool()
        tool._run = MagicMock(return_value="HTTP 200\n\nOK")
        result = await tool._arun("https://example.com")
        assert result == "HTTP 200\n\nOK"
        tool._run.assert_called_once_with("https://example.com")

    @patch("app.llm.url_fetch_tool.httpx.Client")
    def test_run_strips_url_whitespace(self, mock_client_cls):
        from app.llm.url_fetch_tool import URLFetchTool

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>OK</body></html>"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        tool = URLFetchTool()
        tool._run("  https://example.com  ")
        mock_client.get.assert_called_once_with("https://example.com", follow_redirects=True)


# ---------------------------------------------------------------------------
# auth/dependencies.py
# ---------------------------------------------------------------------------


class TestAuthDependencies:
    """Tests for app.auth.dependencies (unit-level, mocking DB and JWT)."""

    async def test_get_current_user_no_token(self):
        from app.auth.dependencies import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=None, db=MagicMock())
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail

    @patch("app.auth.dependencies.decode_token")
    async def test_get_current_user_invalid_token(self, mock_decode):
        from jose import JWTError
        from app.auth.dependencies import get_current_user

        mock_decode.side_effect = JWTError("bad token")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="bad-jwt", db=MagicMock())
        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail

    @patch("app.auth.dependencies.decode_token")
    async def test_get_current_user_wrong_token_type(self, mock_decode):
        from app.auth.dependencies import get_current_user

        mock_decode.return_value = {"type": "refresh", "sub": "user-1"}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="refresh-token", db=MagicMock())
        assert exc_info.value.status_code == 401
        assert "Invalid token type" in exc_info.value.detail

    @patch("app.auth.dependencies.decode_token")
    async def test_get_current_user_no_sub(self, mock_decode):
        from app.auth.dependencies import get_current_user

        mock_decode.return_value = {"type": "access"}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="token-no-sub", db=MagicMock())
        assert exc_info.value.status_code == 401
        assert "Invalid token payload" in exc_info.value.detail

    @patch("app.auth.dependencies.decode_token")
    async def test_get_current_user_user_not_found(self, mock_decode):
        from app.auth.dependencies import get_current_user

        mock_decode.return_value = {"type": "access", "sub": "missing-id"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="valid-token", db=mock_db)
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail

    @patch("app.auth.dependencies.decode_token")
    async def test_get_current_user_success(self, mock_decode):
        from app.auth.dependencies import get_current_user

        mock_decode.return_value = {"type": "access", "sub": "user-123"}

        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        user = await get_current_user(token="good-token", db=mock_db)
        assert user.id == "user-123"

    def test_require_admin_allows_admin(self):
        from app.auth.dependencies import require_admin

        mock_user = MagicMock()
        mock_user.role = "admin"
        result = require_admin(user=mock_user)
        assert result is mock_user

    def test_require_admin_rejects_non_admin(self):
        from app.auth.dependencies import require_admin

        mock_user = MagicMock()
        mock_user.role = "user"
        with pytest.raises(HTTPException) as exc_info:
            require_admin(user=mock_user)
        assert exc_info.value.status_code == 403

    @patch("app.auth.dependencies.decode_token")
    async def test_get_current_user_from_query_no_token(self, mock_decode):
        from app.auth.dependencies import get_current_user_from_query

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_from_query(token=None, db=MagicMock())
        assert exc_info.value.status_code == 401

    @patch("app.auth.dependencies.decode_token")
    async def test_get_current_user_from_query_invalid(self, mock_decode):
        from jose import JWTError
        from app.auth.dependencies import get_current_user_from_query

        mock_decode.side_effect = JWTError("expired")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_from_query(token="expired-jwt", db=MagicMock())
        assert exc_info.value.status_code == 401

    @patch("app.auth.dependencies.decode_token")
    async def test_get_current_user_from_query_wrong_type(self, mock_decode):
        from app.auth.dependencies import get_current_user_from_query

        mock_decode.return_value = {"type": "refresh", "sub": "user-1"}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_from_query(token="wrong-type", db=MagicMock())
        assert exc_info.value.status_code == 401
        assert "Invalid token type" in exc_info.value.detail

    @patch("app.auth.dependencies.decode_token")
    async def test_get_current_user_from_query_user_not_found(self, mock_decode):
        from app.auth.dependencies import get_current_user_from_query

        mock_decode.return_value = {"type": "access", "sub": "missing-id"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_from_query(token="valid", db=mock_db)
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail

    async def test_get_verified_profile_not_found(self):
        from app.auth.dependencies import get_verified_profile

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_user.role = "user"

        with pytest.raises(HTTPException) as exc_info:
            await get_verified_profile(profile_id="nope", user=mock_user, db=mock_db)
        assert exc_info.value.status_code == 404

    async def test_get_verified_profile_wrong_owner(self):
        from app.auth.dependencies import get_verified_profile

        mock_profile = MagicMock()
        mock_profile.owner_id = "other-user"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_profile
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_user.role = "user"

        with pytest.raises(HTTPException) as exc_info:
            await get_verified_profile(profile_id="p-1", user=mock_user, db=mock_db)
        assert exc_info.value.status_code == 403

    async def test_get_verified_profile_admin_bypass(self):
        from app.auth.dependencies import get_verified_profile

        mock_profile = MagicMock()
        mock_profile.owner_id = "other-user"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_profile
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_user = MagicMock()
        mock_user.id = "admin-1"
        mock_user.role = "admin"

        result = await get_verified_profile(profile_id="p-1", user=mock_user, db=mock_db)
        assert result is mock_profile


# ---------------------------------------------------------------------------
# auth/email.py
# ---------------------------------------------------------------------------


class TestAuthEmail:
    """Tests for app.auth.email send helpers."""

    @patch("app.auth.email.settings")
    def test_send_verification_email_smtp_not_configured(self, mock_settings):
        from app.auth.email import send_verification_email

        mock_settings.smtp_host = ""
        mock_settings.smtp_from_email = ""
        mock_settings.app_base_url = "http://localhost:8000"

        # Should not raise -- just logs a warning and returns
        send_verification_email("test@example.com", "tok123")

    @patch("app.auth.email.smtplib.SMTP")
    @patch("app.auth.email.settings")
    def test_send_verification_email_success(self, mock_settings, mock_smtp_cls):
        from app.auth.email import send_verification_email

        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "noreply@test.com"
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"
        mock_settings.app_base_url = "http://localhost:8000"

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_verification_email("test@example.com", "tok123")

        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert args[0] == "noreply@test.com"
        assert args[1] == "test@example.com"

    @patch("app.auth.email.smtplib.SMTP")
    @patch("app.auth.email.settings")
    def test_send_password_reset_email_success(self, mock_settings, mock_smtp_cls):
        from app.auth.email import send_password_reset_email

        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "noreply@test.com"
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.app_base_url = "http://localhost:8000"

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_password_reset_email("reset@example.com", "reset-tok")

        mock_server.starttls.assert_called_once()
        # No login when smtp_user is empty
        mock_server.login.assert_not_called()
        mock_server.sendmail.assert_called_once()

    @patch("app.auth.email.smtplib.SMTP")
    @patch("app.auth.email.settings")
    def test_send_handles_smtp_exception(self, mock_settings, mock_smtp_cls):
        from app.auth.email import send_verification_email

        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "noreply@test.com"
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.app_base_url = "http://localhost:8000"

        mock_smtp_cls.return_value.__enter__ = MagicMock(
            side_effect=smtplib.SMTPException("Connection refused")
        )
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Should not raise
        send_verification_email("test@example.com", "tok")


# ---------------------------------------------------------------------------
# auth/oauth.py
# ---------------------------------------------------------------------------


class TestAuthOAuth:
    """Tests for app.auth.oauth Google OAuth helpers."""

    @patch("app.auth.oauth.settings")
    def test_get_google_auth_url(self, mock_settings):
        from app.auth.oauth import get_google_auth_url

        mock_settings.google_client_id = "test-client-id"

        url = get_google_auth_url("http://localhost/callback")
        assert "accounts.google.com" in url
        assert "test-client-id" in url
        assert "redirect_uri=" in url

    @patch("app.auth.oauth.httpx.AsyncClient")
    @patch("app.auth.oauth.settings")
    async def test_exchange_google_code_success(self, mock_settings, mock_client_cls):
        from app.auth.oauth import exchange_google_code

        mock_settings.google_client_id = "client-id"
        mock_settings.google_client_secret = "client-secret"

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "goog-token"}
        mock_token_resp.raise_for_status = MagicMock()

        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.json.return_value = {
            "email": "user@gmail.com",
            "given_name": "Test",
            "family_name": "User",
            "sub": "google-id-123",
            "email_verified": True,
        }
        mock_userinfo_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_token_resp
        mock_client.get.return_value = mock_userinfo_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await exchange_google_code("auth-code", "http://localhost/callback")
        assert result["email"] == "user@gmail.com"
        assert result["first_name"] == "Test"
        assert result["last_name"] == "User"
        assert result["google_id"] == "google-id-123"
        assert result["email_verified"] is True

    @patch("app.auth.oauth.httpx.AsyncClient")
    @patch("app.auth.oauth.settings")
    async def test_exchange_google_code_missing_optional_fields(self, mock_settings, mock_client_cls):
        from app.auth.oauth import exchange_google_code

        mock_settings.google_client_id = "client-id"
        mock_settings.google_client_secret = "client-secret"

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "goog-token"}
        mock_token_resp.raise_for_status = MagicMock()

        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.json.return_value = {
            "email": "minimal@gmail.com",
            "sub": "gid-456",
        }
        mock_userinfo_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_token_resp
        mock_client.get.return_value = mock_userinfo_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await exchange_google_code("code", "http://localhost/cb")
        assert result["first_name"] == ""
        assert result["last_name"] == ""
        assert result["email_verified"] is False

    @patch("app.auth.oauth.httpx.AsyncClient")
    @patch("app.auth.oauth.settings")
    async def test_exchange_google_code_token_error(self, mock_settings, mock_client_cls):
        from app.auth.oauth import exchange_google_code
        import httpx as _httpx

        mock_settings.google_client_id = "cid"
        mock_settings.google_client_secret = "cs"

        mock_token_resp = MagicMock()
        mock_token_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "bad request", request=MagicMock(), response=MagicMock()
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_token_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(_httpx.HTTPStatusError):
            await exchange_google_code("bad-code", "http://localhost/cb")


# ---------------------------------------------------------------------------
# main.py helpers
# ---------------------------------------------------------------------------


class TestMainHelpers:
    """Tests for app.main helper functions."""

    async def test_spa_catch_all_no_index(self):
        """When index.html does not exist, return 404 JSON."""
        from app.main import spa_catch_all

        with patch("app.main.spa_dir", Path("/nonexistent/spa")):
            resp = await spa_catch_all("")
            # JSONResponse with 404
            assert resp.status_code == 404

    async def test_spa_catch_all_serves_index(self, tmp_path: Path):
        """When index.html exists, return it for empty path."""
        from app.main import spa_catch_all

        index = tmp_path / "index.html"
        index.write_text("<html>SPA</html>")

        with patch("app.main.spa_dir", tmp_path):
            resp = await spa_catch_all("")
            assert resp.status_code == 200

    async def test_spa_catch_all_serves_static_file(self, tmp_path: Path):
        """When a static file exists in spa_dir, serve it directly."""
        from app.main import spa_catch_all

        favicon = tmp_path / "favicon.svg"
        favicon.write_text("<svg/>")

        with patch("app.main.spa_dir", tmp_path):
            resp = await spa_catch_all("favicon.svg")
            assert resp.status_code == 200

    async def test_spa_catch_all_fallback_to_index(self, tmp_path: Path):
        """Unknown paths should fall back to index.html for client-side routing."""
        from app.main import spa_catch_all

        index = tmp_path / "index.html"
        index.write_text("<html>SPA</html>")

        with patch("app.main.spa_dir", tmp_path):
            resp = await spa_catch_all("some/deep/route")
            assert resp.status_code == 200

    @patch("app.main.recover_orphaned_runs", new_callable=AsyncMock)
    @patch("app.main._ensure_admin", new_callable=AsyncMock)
    @patch("app.main.engine")
    async def test_lifespan_creates_tables(self, mock_engine, mock_admin, mock_recover):
        """lifespan should call create_all and _ensure_admin."""
        from app.main import lifespan

        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()

        mock_begin = AsyncMock()
        mock_begin.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_begin.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = mock_begin

        mock_app = MagicMock()
        async with lifespan(mock_app):
            pass

        mock_conn.run_sync.assert_called_once()
        mock_admin.assert_awaited_once()
        mock_recover.assert_awaited_once()
