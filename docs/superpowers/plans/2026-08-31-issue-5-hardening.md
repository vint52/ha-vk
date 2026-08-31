# Issue #5: Reliability Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all improvements from GitHub issue #5: session leak fix, typed API exceptions, resilient receiver with backoff, random_id dedup, `entry.runtime_data`, reauth flow, and test/polish items.

**Architecture:** Typed exceptions (`VkAuthError`, `VkNetworkError`, `VkLongPollError`) become the foundation in `api.py`; config flow and receiver then dispatch on type instead of message substrings. Receiver becomes a config-entry background task with exponential backoff and triggers reauth on auth errors. Entry state moves from `hass.data[DOMAIN]` to `entry.runtime_data` (typed alias lives in `receiver.py` to avoid import cycles).

**Tech Stack:** Home Assistant ≥2025.3 (already required by `AddConfigEntryEntitiesCallback` in notify.py), aiohttp, pytest + pytest-homeassistant-custom-component. Tests run with `.venv/bin/python -m pytest -q`, lint with `.venv/bin/ruff check custom_components tests`.

**Branch:** `feature/issue-5-hardening` off `refactor/cleanup`.

---

### Task 1: Typed exceptions in api.py

**Files:**
- Modify: `custom_components/ha_vk/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing tests** for: `_api_call` raising `VkAuthError` with `code` on VK auth error codes (5/15/27/28), `VkNetworkError` on network failure, `async_get_long_poll_server`/`async_check_long_poll` raising `VkLongPollError`, video fallback to document on `VkAuthError(code=27)`, and `is_auth_error` helper.
- [ ] **Step 2: Run tests, verify they fail** (`ImportError: cannot import name 'VkAuthError'`).
- [ ] **Step 3: Implement** in `api.py`:
  - `VkApiError.__init__(self, message, code: int | None = None)` storing `self.code`.
  - Subclasses `VkAuthError`, `VkNetworkError`, `VkLongPollError`.
  - Constants `VK_ERROR_AUTH_FAILED = 5`, `VK_ERROR_ACCESS_DENIED = 15`, `VK_ERROR_GROUP_AUTH_FAILED = 27`, `VK_ERROR_APP_AUTH_FAILED = 28`, `VK_AUTH_ERROR_CODES = frozenset({5, 15, 27, 28})`.
  - `is_auth_error(err)` → `isinstance(err, VkAuthError) or err.code in VK_AUTH_ERROR_CODES`.
  - `_api_call`: network except → `VkNetworkError`; VK error payload → parse `error_code`, raise `VkAuthError` if code in set else `VkApiError` (both with `code=`).
  - `async_get_long_poll_server`: wrap `VkApiError` from `_api_call` into `VkLongPollError(str(err), code=err.code)`; parse errors → `VkLongPollError`.
  - `async_check_long_poll`: all raises become `VkLongPollError` (network included).
  - `_upload_video_attachment`: `except VkAuthError`: code 27 → document fallback, else raise `VkAuthError("VK wall access token is invalid", code=err.code)`. Delete `_is_invalid_token_error`.
- [ ] **Step 4: Update existing test** `test_send_video_with_invalid_wall_token_raises_clear_error` to raise `VkAuthError("video.save: invalid access token", code=5)`.
- [ ] **Step 5: Run full suite, verify pass.**
- [ ] **Step 6: Commit** `feat: typed VK API exceptions with error codes`.

### Task 2: Config flow — shared session + type-based error mapping

**Files:**
- Modify: `custom_components/ha_vk/config_flow.py`
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing test** that `_async_validate_input` uses `async_get_clientsession(hass)` (patch `config_flow.VkClient`, assert first arg is the shared session).
- [ ] **Step 2: Verify fail.**
- [ ] **Step 3: Implement:** replace `async_create_clientsession` with `async_get_clientsession`; rewrite `_validation_error_key` to isinstance checks (`VkConfigError` → `invalid_input`/`incoming_not_available` as now; `VkLongPollError` → `incoming_not_available`; `VkAuthError` → `invalid_auth`; `VkNetworkError` → `cannot_connect`; else `vk_error`).
- [ ] **Step 4: Update existing test** `test_user_flow_surfaces_incoming_message_setup_errors` to use `VkLongPollError`.
- [ ] **Step 5: Run suite, verify pass. Commit** `fix: reuse shared aiohttp session and map validation errors by exception type`.

### Task 3: Random random_id for message dedup

**Files:**
- Modify: `custom_components/ha_vk/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing test:** plain-text `async_send_message` (with `_api_call` mocked) passes a nonzero `random_id`; two calls produce different values.
- [ ] **Step 2: Verify fail. Step 3: Implement** `_random_id()` using `secrets.randbelow(2**31 - 1) + 1`; use in both `messages.send` call sites.
- [ ] **Step 4: Run suite, verify pass. Commit** `fix: send random random_id so VK deduplication works`.

### Task 4: Receiver hardening

**Files:**
- Modify: `custom_components/ha_vk/receiver.py`, `custom_components/ha_vk/const.py`, `custom_components/ha_vk/__init__.py`
- Test: `tests/test_receiver.py`

- [ ] **Step 1: Write failing tests:** receiver survives an unexpected `KeyError` from `async_check_long_poll` and keeps emitting events afterwards (patch `asyncio.sleep` or use small delay); receiver calls `entry.async_start_reauth` and stops on `VkAuthError`.
- [ ] **Step 2: Verify fail. Step 3: Implement:**
  - Constructor takes `entry: ConfigEntry` instead of `entry_id`; task created via `entry.async_create_background_task(hass, self._async_run(), name=...)`.
  - `const.py`: add `LONG_POLL_MAX_RETRY_DELAY = 300.0`.
  - `_async_run`: keep `CancelledError` re-raise; single `except Exception` branch: if `VkApiError` and `is_auth_error(err)` → `LOGGER.error` + `entry.async_start_reauth(hass)` + return; if `VkApiError` → `LOGGER.warning`; else `LOGGER.exception`; then `server = None`, sleep `retry_delay`, `retry_delay = min(retry_delay * 2, LONG_POLL_MAX_RETRY_DELAY)`. Successful iteration resets `retry_delay` to `LONG_POLL_RETRY_DELAY`.
  - `__init__.py`: pass `entry` to receiver.
- [ ] **Step 4: Update existing receiver test** to construct with a `MockConfigEntry` added to hass.
- [ ] **Step 5: Run suite, verify pass. Commit** `fix: receiver survives unexpected errors with exponential backoff, triggers reauth`.

### Task 5: Reauth flow + abort strings

**Files:**
- Modify: `custom_components/ha_vk/config_flow.py`, `custom_components/ha_vk/strings.json`, `custom_components/ha_vk/translations/en.json`, `custom_components/ha_vk/translations/ru.json`
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing test:** start flow with `SOURCE_REAUTH` context for an existing entry, submit a new token with validation patched, assert `ABORT` with reason `reauth_successful` and updated `entry.data[CONF_VK_ACCESS_TOKEN]`.
- [ ] **Step 2: Verify fail. Step 3: Implement** `async_step_reauth` → `async_step_reauth_confirm` (password fields for `vk_access_token` + optional `vk_wall_access_token`), validate merged config, `self.async_update_reload_and_abort(entry, data=..., options=...)`.
- [ ] **Step 4: strings/translations:** add `config.step.reauth_confirm` (title, description, data labels), `config.abort.already_configured` and `config.abort.reauth_successful` to `strings.json`, `en.json`, `ru.json` (Russian text for ru).
- [ ] **Step 5: Run suite, verify pass. Commit** `feat: reauth flow and config abort strings`.

### Task 6: Migrate to entry.runtime_data

**Files:**
- Modify: `custom_components/ha_vk/receiver.py` (add `type HaVkConfigEntry = ConfigEntry[HaVkEntryRuntime]`), `custom_components/ha_vk/__init__.py`, `custom_components/ha_vk/notify.py`, `custom_components/ha_vk/services.py`, `hacs.json`
- Test: `tests/test_services.py`, `tests/test_init.py`

- [ ] **Step 1: Update tests first:** services test builds a `MockConfigEntry`, sets `entry.runtime_data = HaVkEntryRuntime(client=client)`, `entry.mock_state(hass, ConfigEntryState.LOADED)`; add test that `hass.data` no longer holds DOMAIN runtimes after setup (or assert `entry.runtime_data.client` set in init test).
- [ ] **Step 2: Verify fail. Step 3: Implement:**
  - `receiver.py`: `type HaVkConfigEntry = ConfigEntry[HaVkEntryRuntime]`.
  - `__init__.py`: drop `async_setup`; store runtime in `entry.runtime_data`; unregister services when no other loaded entries remain (`hass.config_entries.async_loaded_entries(DOMAIN)` excluding current entry_id).
  - `notify.py`: `entry.runtime_data.client`.
  - `services.py`: `_resolve_client` iterates `hass.config_entries.async_loaded_entries(DOMAIN)`.
  - `hacs.json`: add `"homeassistant": "2025.3.0"`.
- [ ] **Step 4: Run suite, verify pass. Commit** `refactor: store runtime state in entry.runtime_data`.

### Task 7: Polish — API version default + missing test coverage

**Files:**
- Modify: `custom_components/ha_vk/const.py`
- Test: `tests/test_notify.py` (new), `tests/test_api.py`

- [ ] **Step 1:** `DEFAULT_API_VERSION = "5.199"`.
- [ ] **Step 2: New tests:**
  - `tests/test_notify.py`: full entry setup with patched `VkClient.async_send_message`; call `notify.send_message` on the created entity; assert forwarded message/title.
  - `tests/test_api.py`: wall post with image + wall token calls `_upload_wall_photo` and passes `attachments`; video upload falls back to document on `VkAuthError(code=27)` (covered in Task 1 — keep if present).
- [ ] **Step 3: Run suite + ruff, verify pass. Commit** `test: cover notify entity and wall photo posts; bump default VK API version`.

### Task 8: Final verification & changelog

- [ ] **Step 1:** `.venv/bin/python -m pytest -q` — all pass.
- [ ] **Step 2:** `.venv/bin/ruff check custom_components tests` — clean.
- [ ] **Step 3:** Add Unreleased section to `CHANGELOG.md` describing the fixes (session leak, typed errors, receiver backoff/reauth, random_id, runtime_data, reauth flow, strings).
- [ ] **Step 4: Commit** `docs: changelog for issue #5 hardening`.
